import socket
import threading

HOST = '127.0.0.1'
PORT = 8080

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server_socket.bind((HOST, PORT))
server_socket.listen(5)

print('Server is listening...')

while True:
    # 3. Accept a client connection
    client_socket, client_addr = server_socket.accept()
    print(f"Connection from {client_addr}")

    # 4. Receive data (up to 1024 bytes)
    data = client_socket.recv(1024)
    print(f"Received: {data}")

    # 5. Send raw response
    client_socket.sendall(b"Hello from raw TCP server!\n")

    # 6. Close connection
    client_socket.close()