let currentSessionId = null;
const chatBox = document.getElementById("chat-box");
const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const fileInput = document.getElementById("file-upload");
const micBtn = document.getElementById("mic-btn");
const sessionList = document.getElementById("session-list");
const chatForm = document.getElementById("chat-form");

const sidebar = document.getElementById("sidebar");
const main = document.getElementById("main-container");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarClose = document.getElementById("sidebar-close");

const chatLog = [];

const isGuest = sessionStorage.getItem("isGuest") === "true";

let guestId = sessionStorage.getItem("guest_id");

function generateGuestId() {
    const id = "guest_" +  crypto.randomUUID();
    sessionStorage.setItem("guest_id", id);
    return id;
}

if (isGuest && !guestId) {
    guestId = generateGuestId();
}

if (isGuest) {
  document.getElementById("profile-menu").style.display = "none";
  document.getElementById("login-btn").style.display = "inline-block";
  document.getElementById("main-container").style.marginLeft = "0px";
} else {
  document.getElementById("profile-menu").style.display = "block";
  document.getElementById("login-btn").style.display = "none";
}

// if (isGuest) {
//     document.getElementById("sidebar").classList.add("hidden");
//     document.getElementById("logout-btn").innerText = "Login";
//     document.getElementById("logout-btn").onclick = () => {
//         sessionStorage.removeItem("isGuest");
//         window.location.href = "/login";
//     };
// } else {
//     // ✅ Restore logout button text and action
//     const logoutBtn = document.getElementById("logout-btn");
//     logoutBtn.innerText = "Logout";
//     logoutBtn.onclick = logout;
// }

const uploadBtn = document.querySelector(".upload-btn");
uploadBtn.addEventListener("click", () => {
    fileInput.value = "";
    fileInput.click();
});

sendBtn.onclick = async () => {
    const question = input.value.trim();
    if (!question) return;

    addMessage("user", question);
    input.value = "";

    const res = await fetch("/ask", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...(isGuest ? { "X-Guest-ID": guestId } : {})
        },
        body: JSON.stringify({ question, session_id: currentSessionId })
    });

    const data = await res.json();
    const answer = data.answer || data.error || "No response.";
    addMessage("bot", answer);
    chatLog.push({ question, answer });
};

const showOverlay = () => {
    document.getElementById("uploading-overlay").style.display = "flex";
};

const hideOverlay = () => {
    document.getElementById("uploading-overlay").style.display = "none";
};

fileInput.onchange = async () => {
    const files = fileInput.files;
    if (!files.length) return;

    const uploadedFileName = files[0].name.replace(/[<>:"/\\|?*]+/g, '').trim();

    if (!currentSessionId && !isGuest) {
        try {
            const res = await fetch("/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: `Chat-(${uploadedFileName})` })
            });

            const contentType = res.headers.get("content-type");
            if (!contentType || !contentType.includes("application/json")) {
                const text = await res.text();
                throw new Error("Expected JSON but got HTML:\n" + text.slice(0, 100));
            }

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "Session creation failed");

            currentSessionId = data.session_id;
            loadSessions();
        } catch (err) {
            console.error("Session creation failed:", err.message);
            addMessage("bot", "⚠️ Error creating session.");
            return;
        }
    }

    const formData = new FormData();
    for (const file of files) {
        formData.append("file", file);
    }

    if (isGuest && guestId) {
        formData.append("guest_id", guestId);               // ✅ guest folder identifier
    } else {
        formData.append("session_id", currentSessionId);    // ✅ for logged-in users
    }


    try {
        showOverlay();
        const res = await fetch("/upload", {
            method: "POST",
            body: formData
        });

        const contentType = res.headers.get("content-type");
        let data = {};

        if (contentType && contentType.includes("application/json")) {
            data = await res.json();
            if (isGuest && data.session_id) {
                 currentSessionId = data.session_id;
            }
            console.log("[UPLOAD] Guest Session ID Set:", currentSessionId);
            console.log("[UPLOAD] Guest ID:", guestId);


        } else {
            const text = await res.text();
            throw new Error("Expected JSON but got HTML:\n" + text.slice(0, 100));
        }

        if (!res.ok) throw new Error(data.error || "Upload failed");

        for (const file of files) {
            const uploadedFileName = file.name.replace(/[<>:"/\\|?*]+/g, '').trim();
            addMessage("bot", `🗂 Uploaded File: ${uploadedFileName}`);
        }

    } catch (err) {
        console.error("Upload failed:", err.message);
        alert("File cannot be uploaded:\n" + err.message);
    } finally {
        hideOverlay();
    }
};

micBtn.onclick = () => {
    const recognition = new webkitSpeechRecognition();
    recognition.lang = "en-US";
    recognition.start();
    recognition.onresult = (event) => {
        input.value = event.results[0][0].transcript;
    };
};

function addMessage(sender, text) {
    if (!text || !text.trim()) return;
    const msg = document.createElement("div");
    msg.className = `message ${sender}`;
    msg.innerText = text;
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
}

document.getElementById("download-log").onclick = async () => {
  // default name if we can't fetch /sessions (guest)
  let sessionTitle = "chat_log";
  const dateStamp = new Date().toISOString().split("T")[0];

  try {
    const res = await fetch("/sessions", { headers: { "Accept": "application/json" } });
    const isJSON = res.headers.get("content-type")?.includes("application/json");
    if (res.ok && isJSON) {
      const sessions = await res.json();
      const session = sessions.find(s => String(s.id) === String(currentSessionId));
      if (session?.title) {
        sessionTitle = session.title.replace(/[^a-z0-9]/gi, "_").toLowerCase();
      }
    }
    // if not ok or not JSON (guest redirect), we keep the default "chat_log"
  } catch {
    // network error: keep default "chat_log"
  }

  const filename = `${sessionTitle}_${dateStamp}.txt`;

  const lines = (Array.isArray(chatLog) ? chatLog : []).map(e => {
    if (!e.question && e.answer?.startsWith("🗂 Uploaded File:")) {
      return `${e.answer}\n\n`;
    } else {
      return `Q: ${e.question}\nA: ${e.answer}\n\n`;
    }
  }).join("");

  const blob = new Blob([lines], { type: "text/plain" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
};

async function logout() {
    await fetch("/logout", { method: "POST" });
    window.location.href = "/";
}

async function createNewChat() {
    const now = new Date();
    const defaultTitle = `Chat-${now.toLocaleDateString("en-US")}`; // MM/DD/YYYY format

    // Show prompt with default value filled in
    let title = prompt("Enter a title for this chat:", defaultTitle);

    //  User cancelled → don't create
    if (title === null) return;

    // Trim input and reject empty string
    title = title.trim();
    if (!title) return;

    const res = await fetch("/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title })
    });
    const data = await res.json();
    currentSessionId = data.session_id;
    loadSessions();
    chatBox.innerHTML = "";
    chatLog.length = 0;
}

async function loadSessions() {
    const res = await fetch("/sessions");
    const sessions = await res.json();
    sessionList.innerHTML = "";
    sessions.forEach(s => {
        const li = document.createElement("li");
        li.innerText = s.title;
        li.onclick = () => loadSessionChat(s.id);
        if (s.id === currentSessionId) li.classList.add("active");

        const renameBtn = document.createElement("button");
        renameBtn.innerHTML = '<i class="fa-solid fa-pen" style="color: #101010;"></i>';
        renameBtn.style.marginLeft = "auto";
        renameBtn.style.backgroundColor = "#EAEAEA";
        renameBtn.onclick = async (e) => {
            e.stopPropagation();
            const newTitle = prompt("Enter new title:", s.title);
            if (!newTitle) return;
            await fetch(`/session/${s.id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: newTitle })
            });
            loadSessions();
        };

        const delBtn = document.createElement("button");
        delBtn.innerHTML = '<i class="fa-solid fa-trash" style="color: #101010;"></i>';
        delBtn.style.marginLeft = "5px";
        delBtn.style.backgroundColor = "#EAEAEA";
        delBtn.onclick = async (e) => {
            e.stopPropagation();
            try {
                const res = await fetch(`/session/${s.id}`, { method: "DELETE" });
                if (!res.ok) {
                    const err = await res.text();
                    alert("Failed to delete session:\n" + err);
                }
            } catch (e) {
                alert("Error deleting session: " + e.message);
            }

            if (s.id === currentSessionId) {
                currentSessionId = null;
                chatBox.innerHTML = "";
            }
            loadSessions();
        };

        li.appendChild(renameBtn);
        li.appendChild(delBtn);
        sessionList.appendChild(li);
    });
}

async function loadSessionChat(sessionId) {
    currentSessionId = sessionId;
    const res = await fetch(`/history/${sessionId}`);
    const data = await res.json();
    chatBox.innerHTML = "";
    chatLog.length = 0;
    data.forEach(entry => {
        if (entry.question && entry.question.trim()) {
            addMessage("user", entry.question);
        }
        if (entry.answer && entry.answer.trim()) {
            addMessage("bot", entry.answer);
        }
        chatLog.push({ question: entry.question, answer: entry.answer });
    });
    loadSessions();
}

chatForm.onsubmit = async (e) => {
    e.preventDefault();
    sendBtn.click();
};

sidebarToggle.style.display = "none";

sidebarClose.onclick = () => {
    sidebar.classList.add("hidden");
    sidebarToggle.style.display = "block";
};

sidebarToggle.onclick = () => {
    sidebar.classList.remove("hidden");
    sidebarToggle.style.display = "none";
};

window.onload = async () => {
    const overlay = document.getElementById("session-loading-overlay");

    if (isGuest) {
        // ✅ Guest UI: disable sidebar, login instead of logout
        document.getElementById("sidebar").style.display = "none";
        document.getElementById("sidebar-toggle").style.display = "none";
        document.getElementById("sidebar-close").style.display = "none";

        const logoutBtn = document.getElementById("logout-btn");
        logoutBtn.innerText = "Login";
        logoutBtn.onclick = () => {
            sessionStorage.removeItem("isGuest");
            window.location.href = "/login";
        };

        overlay.style.display = "none";
        return; // Skip reload_chains and session load
    }

    // ✅ Logged-in user flow
    overlay.style.display = "flex";
    try {
        await fetch("/reload_chains", {
            method: "POST",
            credentials: "include"
        });
    } catch (e) {
        console.warn("Chain reload failed:", e.message);
    } finally {
        overlay.style.display = "none";
        loadSessions();  // show sidebar + sessions
    }
};

window.addEventListener("beforeunload", () => {
    if (isGuest && guestId) {
        navigator.sendBeacon("/cleanup_guest", JSON.stringify({ guest_id: guestId }));
    }
});

