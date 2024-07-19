from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, status
from collections import defaultdict
from fastapi.responses import HTMLResponse, JSONResponse
import uuid
from pydantic import BaseModel
from fastapi import Cookie
import json
import asyncio
from fastapi.middleware.cors import CORSMiddleware

origins = ["http://localhost:3000","http://localhost",]


class User(BaseModel):
    username: str

users = {}
conversations = defaultdict(list)
users_by_username = {}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # Set to True if cookies are passed
    allow_methods=["*"],  # Allow all HTTP methods (adjust as needed)
    allow_headers=["*"],  # Allow all headers (adjust as needed)
)

html = """
 <!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chat App</title>
</head>
<body>
<h1>Chat Room</h1>
<div id="chat-messages"></div>
<input type="text" id="message" placeholder="Enter message">
<input type="text" id="recipient" placeholder="Username (private)"> <button id="send-button">Send</button>
<script>
const ws = new WebSocket("ws://localhost:8000/ws/" + prompt("Enter your username:"));
const messageInput = document.getElementById("message");
const recipientInput = document.getElementById("recipient");
const sendMessageButton = document.getElementById("send-button");
const chatMessages = document.getElementById("chat-messages");

sendMessageButton.addEventListener("click", () => {
    const message = messageInput.value;
    const recipient = recipientInput.value || "all";
    ws.send(`${message}:${recipient}`);
    messageInput.value = "";
});

ws.onmessage = (event) => {
    const message = event.data;
    chatMessages.innerHTML += `<p>${message}</p>`;
};</script>
</body>
</html>
"""

class ConnectionManager:
    def __init__(self):
        self.connections = defaultdict(list)
        self.recipient_map = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        self.connections[client_id].append(websocket)
        await websocket.accept()

    async def disconnect(self, websocket: WebSocket, client_id: str):
        self.connections[client_id].remove(websocket)

    async def send_private_message(self, sender_id: str, recipient_id: str, message: str):
        for ws in self.connections[recipient_id]:
            await ws.send_text(f"{sender_id}: {message}")

            
manager = ConnectionManager()


@app.get("/")
async def get():
    return HTMLResponse(html)

@app.get("/active_users")
async def active_users(access_token: str | None = Cookie(None)):
    requested_users_list = set(users_by_username.keys())
    if access_token in users:
        requester = users[access_token].username
        requested_users_list -= set([requester])
        return JSONResponse(content=json.dumps(list(requested_users_list)))
    return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Unauthorized", "error_code": "401"}
        )

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            recipient_id,message = data.split(':')
            print(manager.connections)
            await manager.send_private_message(client_id, recipient_id, message)
            chat_room = tuple(sorted([client_id, recipient_id]))
            conversations[chat_room].append(client_id+":"+message)
            manager.recipient_map[client_id] = recipient_id
    except asyncio.CancelledError:
        pass
    finally:
        await manager.disconnect(websocket, client_id)
        del manager.recipient_map[client_id]
        
@app.get('/chat_history')
async def provide_token(user_1: str, user_2:  str):
    chat_room = tuple(sorted([user_1, user_2]))
    if chat_room in conversations:
        return JSONResponse(content=json.dumps(conversations[chat_room]))
    return JSONResponse(content=json.dumps([]))
          

@app.get("/token")
async def privide_token(user:  User = Depends(User)):
    token = str(uuid.uuid4())
    response = JSONResponse(content=token)
    # Set the cookie (adjust attributes as needed)
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=3600,  # Expires in 1 hour (adjust as needed)
        httponly=True,  # Prevent access from JavaScript for better security
        secure=True,  # Set to True if using HTTPS for added security,
        samesite="None"
    )
    users.update({token: user})
    users_by_username.update({user.username: user})
    print(users)
    return response
    