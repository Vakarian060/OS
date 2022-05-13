import logging
import socket
import select
import threading
import os

from loguru import logger

class FtpServer(threading.Thread):
    def __init__(self, comm_sock, address):
        threading.Thread.__init__(self)
        
        self.cwd = os.getenv("HOME")
        self.comm_sock = comm_sock  
        self.address = address

        self.data_sock_addr='127.0.0.1'
        self.data_sock_port=63111

        self.is_run_on = False

    def run(self):
        poller = select.poll()
        poller.register(self.comm_sock, select.POLLIN)
        self.comm_sock.fileno()

        if self.is_run_on:
            self.send_command('Already running')
            return

        self.send_command('220 Welcome.\r\n')
        
        try:
            self.is_run_on = True

            while True:
                data = None 
                cmd = None 

                socket_event = poller.poll(1000)
                
                for descriptor, event in socket_event:
                    if descriptor == self.comm_sock.fileno():
                        data, _ = self.comm_sock.recvfrom(1024).rstrip()
                        try:
                            cmd = data.decode('utf-8')
                        except AttributeError:
                            cmd = data  
                        
                if not cmd:
                    break    
  
                cmd, arg = cmd[:4].strip().upper(), cmd[4:].strip() or None
                func = getattr(self, cmd)
                func(arg)
        except socket.error as exc:
            logger.info(f"{exc} receive")
        except AttributeError as exc: 
            self.send_command('500 Syntax error, command unrecognized. '
                'This may include errors such as command line too long.\r\n')
            logger.error(exc)
        except Exception as exc_g:
            self.send_command("Unrecognized error occured")
            logging.error(exc_g)
        finally:
            self.is_run_on = False

    def start_data_sock(self):
        try:
            self.data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.data_sock.connect((self.data_sock_addr, self.data_sock_port))
            self.data_sock.setblocking(0)
        except socket.error as exc:
            logger.error(exc)

    def stop_data_sock(self):
        try:
            self.data_sock.close( )
        except socket.error as exc:
            logger.error(exc)

    def send_command(self, cmd):
        self.comm_sock.send(cmd.encode('utf-8'))

    def send_data(self, data):
        self.data_sock.send(data.encode('utf-8'))

    # FTP coms start here 

    def USER(self, user):
        logger.info(f"USER {user}")
        if not user:
            self.send_command('501 Syntax error in parameters or arguments.\r\n')

        else:
            self.send_command('331 User name okay, need password.\r\n')
            self.username = user

    def PASS(self, passwd):
        logger.info(f"PASS {passwd}")
        if not passwd:
            self.send_command('501 Syntax error in parameters or arguments.\r\n')

        elif not self.username:
            self.send_command('503 Bad sequence of commands.\r\n')

        else:
            self.send_command('230 User logged in, proceed.\r\n')
            self.passwd = passwd
            self.authenticated = True

    def TYPE(self, type_):
        logger.info(f"TYPE {type_}")
        self.mode = type_
        if self.mode == 'I':
            self.send_command('200 Binary mode.\r\n')
        elif self.mode == 'A':
            self.send_command('200 Ascii mode.\r\n')

    def PWD(self, cmd):
        logger.info(f"PWD {cmd}")
        self.send_command('257 "%s".\r\n' % self.cwd)
    
    def PASV(self, cmd):
        logger.info(f"PASV {cmd}")
        self.pasv_mode  = True
        self.serverSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serverSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serverSock.bind(("127.0.0.1", 0))
        self.serverSock.listen(5)
        addr, port = self.serverSock.getsockname( )
        self.send_command('227 Entering Passive Mode (%s,%u,%u).\r\n' %
                (','.join(addr.split('.')), port>>8&0xFF, port&0xFF))

    def LIST(self, dirpath):
        if not self.authenticated:
            self.send_command('530 User not logged in.\r\n')
            return

        if not dirpath:
            pathname = os.path.abspath(os.path.join(self.cwd, '.'))
        elif dirpath.startswith(os.path.sep):
            pathname = os.path.abspath(dirpath)
        else:
            pathname = os.path.abspath(os.path.join(self.cwd, dirpath))

        logger.info(f"LIST {pathname}")
        if not self.authenticated:
            self.send_command('530 User not logged in.\r\n')

        elif not os.path.exists(pathname):
            self.send_command('550 LIST failed Path name not exists.\r\n')

        else:
            self.send_command('150 Here is listing.\r\n')
            self.start_data_sock( )
            if not os.path.isdir(pathname):
                st = os.stat(pathname)
                self.data_sock.sock(st+'\r\n')

            else:
                for file in os.listdir(pathname):
                    st = os.stat(os.path.join(pathname, file))
                    self.send_data(st +'\r\n')
            self.stop_data_sock( )
            self.send_command('226 List done.\r\n')

    def CWD(self, dirpath):
        pathname = dirpath.startswith(os.path.sep) and dirpath or os.path.join(self.cwd, dirpath)
        logger.info(f"CWD {pathname}")
        if not os.path.exists(pathname) or not os.path.isdir(pathname):
            self.send_command('550 CWD failed Directory not exists.\r\n')
            return
        self.cwd = pathname
        self.send_command('250 CWD Command successful.\r\n')

    def DELE(self, filename):
        pathname = filename.startswith(os.path.sep) and filename or os.path.join(self.cwd, filename)
        logger.info(f"DELE {pathname}")
        if not self.authenticated:
            self.send_command('530 User not logged in.\r\n')

        elif not os.path.exists(pathname):
            self.send('550 DELE failed File %s not exists.\r\n' % pathname)

        else:
            os.remove(pathname)
            self.send_command('250 File deleted.\r\n')

    def RETR(self, filename):
        pathname = os.path.join(self.cwd, filename)
        logger.info(f"RETR {pathname}")
        if not os.path.exists(pathname):
            return
        try:
            if self.mode=='I':
                file = open(pathname, 'rb')
            else:
                file = open(pathname, 'r')
        except OSError as exc:
            logger.error(f"RETR {exc}")

        self.send_command('150 Opening data connection.\r\n')

        self.start_data_sock( )
        while True:
            data = file.read(1024)
            if not data: break
            self.send_data(data)
        file.close( )
        self.stop_data_sock( )
        self.send_command('226 Transfer complete.\r\n')


    def STOR(self, filename):
        if not self.authenticated:
            self.send_command('530 STOR failed User not logged in.\r\n')
            return

        pathname = os.path.join(self.cwd, filename)
        logger.error(f"STOR {pathname}")
        try:
            if self.mode == 'I':
                file = open(pathname, 'wb')
            else:
                file = open(pathname, 'w')
        except OSError as exc:
            logger.error(f"STOR {exc}")

        self.send_command('150 Opening data connection.\r\n' )
        self.start_data_sock( )

        poller_data = select.poll()
        poller_data.register(self.data_sock, select.POLLIN)
        self.data_sock.fileno()

        while True:
            data = None

            socket_event_data = poller_data.poll(1000)
            for descriptor, event in socket_event_data:
                if descriptor == self.data_sock.fileno():
                    data, _ = self.data_sock.recvfrom(1024)
        
            if not data: 
                break

            file.write(data)
        file.close( )
        self.stop_data_sock( )
        self.send_command('226 Transfer completed.\r\n')
