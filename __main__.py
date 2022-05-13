import threading
import socket

from loguru import logger

from ftp.server import FtpServer

PORT = 1235
HOST = "127.0.0.1"

def start_server_listner( ):
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen_sock.bind((HOST, PORT))
    listen_sock.listen(1)
    listen_sock.setblocking(0)

    logger.info(f"FTP server started on {HOST}:{PORT}")
    while True:
        connection, address = listen_sock.accept( )
        f = FtpServer(connection, address)
        f.start( )

if __name__ == "__main__":
    try: 
        logger.info("FTP server is starting")
        listener = threading.Thread(target=start_server_listner)
        listener.start( )
    except Exception as exc:
        logger.error(exc)
        logger.info("FTP server is stopping")  