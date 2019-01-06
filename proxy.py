from socket import *
from urllib.parse import urlparse
import threading
import sys
import traceback
import datetime
BUFSIZE = 2048
TIMEOUT = 10
CRLF = '\r\n'
lock = False
#invalid usage check
if len(sys.argv) < 2 or len(sys.argv) > 4:
    print("need at least three parameters and require at most five parameters")
    sys.exit()

#default: only port number given
host = "0.0.0.0"
port = int(sys.argv[1])
MT = False
PT = False  

#port number with one option
if len(sys.argv) == 3:
    if sys.argv[2] == "-mt":
        MT = True
    elif sys.argv[2] == "-pt":
        PT = True
    else:
        print("wrong inputs")
        sys.exit()

#port number with two options
if len(sys.argv) == 4:
    if sys.argv[2] == "-mt" and sys.argv[3] == "-pt":
        MT = True
        PT = True
    elif sys.argv[2] == "-pt" and sys.argv[3] == "-mt":
        MT = True
        PT = True
    else:
        print("Wrong inputs")
        sys.exit()


# Dissect HTTP header into line(first line), header(second line to end), body
def parseHTTP(data):    
    #byte to string

    dataArr = data.split(b'\r\n\r\n')
    first = dataArr[0].decode().split(CRLF)
    #line str
    line = first[0]

    body = b''
    if len(dataArr[0]) + 4 != len(data):
        body = data[len(dataArr[0]) + 4:]
    

    #header dict
    header = {}

    for i in range(1,len(first)):
        headerTemp = first[i].split(': ')
        header[headerTemp[0]] = headerTemp[1]
    
    return HTTPPacket(line, header, body)


# Receive HTTP packet with socket
# It support seperated packet receive
def recvData(conn):
    # Set time out for error or persistent connection end
    try:
        conn.settimeout(TIMEOUT)
    except:
        if PT:
            conn.close()
            pass
        pass


    #data received from a connected socket
    data = conn.recv(BUFSIZE)

    while b'\r\n\r\n' not in data:
        data += conn.recv(BUFSIZE)

    packet = parseHTTP(data)
    
    body = packet.body

    # Chunked-Encoding
    if packet.isChunked():
        readed = 0
        while True:
            while b'\r\n' not in body[readed:len(body)]:
                d = conn.recv(BUFSIZE)
                body += d
            size_str = body[readed:len(body)].split(b'\r\n')[0]
            size = int(size_str, 16)
            readed += len(size_str) + 2
            while len(body) - readed < size + 2:
                d = conn.recv(BUFSIZE)
                body += d
            readed += size + 2
            if size == 0: break
        packet.setHeader('Content-Length',str(len(body)))    
    # Content-Length
    elif packet.getHeader('Content-Length'):
        received = 0
        expected = packet.getHeader('Content-Length')
        if expected == None:
            expected = '0'
        expected = int(expected)
        received += len(body)
        
        while received < expected:
            d = conn.recv(BUFSIZE)
            received += len(d)
            body += d

    packet.body = body

    # return packet.pack()
    return packet.pack()

# HTTP packet class
# Manage packet data and provide related functions
class HTTPPacket:
    # Constructer
    def __init__(self, line, header, body):
        self.line = line  # Packet first line(String)
        self.header = header  # Headers(Dict.{Field:Value})
        self.body = body  # Body(Bytes)
    
    # Make encoded packet data
    def pack(self):
        ret = self.line + CRLF
        for field in self.header:
            ret += field + ': ' + self.header[field] + CRLF
        ret += CRLF
        ret = ret.encode()
        ret += self.body
        return ret
    
    # Get HTTP header value
    # If not exist, return empty string
    def getHeader(self, field):
        if field in self.header:
            return self.header[field]
        else:
            return ''
    
    # Set HTTP header value
    # If not exist, add new field
    # If value is empty string, remove field
    def setHeader(self, field, value):
        if field in self.header:
            if value == '':
                del self.header[field]
            else:
                self.header[field] = value
        else:
            if value != '':
                self.header[field] = value

    # Get URL from request packet line
    def getURL(self):
        lineArr = self.line.split(' ')
        return lineArr[1]
    
    def isChunked(self):
        if self.getHeader('Transfer-Encoding'):
            if self.getHeader('Transfer-Encoding') == 'chunked':
                return True
        return False
        #return 'chunked' in self.getHeader('Transfer-Encoding')
        #empty handle

# Proxy handler thread class
class ProxyThread(threading.Thread):
    def __init__(self, conn, addr, counter):
        super().__init__()
        self.conn = conn  # Client socket
        self.addr = addr  # Client address
        self.counter = counter
    # Thread Routine
    def run(self):
        while True:
            try:
                #global lock
                #lock = True

                stringBuffer = ''
                connNow = datetime.datetime.now()
                conndate = connNow.strftime("%d/%b/%Y %H:%M:%S.%f")
                stringBuffer += '[{}] {}\n'.format(self.counter,conndate)
                stringBuffer += '[{}] > Connection from {} {}\n'.format(self.counter,self.addr[0],self.addr[1])
                #when occurs erros from recvData
                try:
                    data = recvData(self.conn)
                except:
                    self.conn.close()
                    pass
                    break
                #when receive none
                if self.conn.fileno() == -1 :
                    self.conn.close()
                    pass
                    break                    
                req = parseHTTP(data)
                url = urlparse(req.getURL())

                # Do I have to do if it is not persistent connection?
                if not PT:
                    req.setHeader('Proxy-Connection', 'close')
                # Remove proxy infomation
                req.setHeader('Connection', req.getHeader('Proxy-Connection'))
                req.setHeader('Proxy-Connection', '')


                # socket created for a Server connection
                svr = socket(AF_INET, SOCK_STREAM)
                svr.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                # and so on...
                #check port number
                port_ = 80
                
                if url.port == None:
                    port_ = 80
                else:
                    port_ = url.port    
                
                #try connect, handle connection fail
                try:
                    svr.connect((url.hostname, port_))
                except Exception as e:
                    # tb = traceback.format_exc()
                    # print(tb)
                    print (e)
                    svr.close()                    
                    sys.exit()
                    
                # send a client's request to the server
                svr.sendall(req.pack())
                # receive data from the server

                data = recvData(svr)
                res = parseHTTP(data)


                res.setHeader('Proxy-Connection', res.getHeader('Connection'))
                res.setHeader('Connection', '')                
                if not PT:
                    res.setHeader('Proxy-Connection', res.getHeader('close'))
                #send back data to connected socket(client)
                #lock = False

                self.conn.sendall(res.pack())

                stringBuffer +='[{}] < {} {}\n'.format(self.counter,res.getHeader('Content-Type'), res.getHeader('Content-Length'))
                stringBuffer +='[{}] < {}\n'.format(self.counter,res.line)
                print(stringBuffer)

                # Set content length header
                
                # If support pc, how to do socket and keep-alive?
                if not PT:
                    self.conn.close()
            except Exception as e:
                # tb = traceback.format_exc()
                # print(tb)
                print (e)
            except KeyboardInterrupt:
                self.conn.close()
                raise KeyboardInterrupt
    
def main():
    try:
        global lock
        lock = False
        counter = 0
        #create a socket objcet
        sock = socket(AF_INET, SOCK_STREAM)
        #prevent Address already in use error
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        
        #binds socket to specific host and port in case of fail close
        try:
            sock.bind((host, port))
        except Exception as e:
            print('Bind failed.')
            sock.close()
            sys.exit()
        #socket listen upto 20
        sock.listen(20)
        now = datetime.datetime.now()
        date = now.strftime("%d/%B/%Y %H:%M:%S.")
        print('Proxy Server started on port %d at %s' % (port, date))
        if MT:
            print('* Multithreading – [ON]')
        elif not MT:
            print('* Multithreading – [OFF]')
        if PT:
            print('* Persistent Connection – [ON]')
        elif not PT:
            print('* Persistent Connection – [OFF]')
        print("")
        #lock = False
        ptOnce = False

        #live server on
        while True:
            try:

                # Client connect
                if MT:
                    conn, addr = sock.accept()
                    counter += 1
                if not MT and not lock:
                    if not ptOnce:
                        conn, addr = sock.accept()
                        counter += 1
                    if PT:
                        ptOnce = True
                # Start Handling
                if MT:
                    pt = ProxyThread(conn, addr, counter)
                    pt.start()
                if not MT and not PT:
                    if not lock:
                        lock = True
                        pt = ProxyThread(conn, addr, counter)
                        pt.start()
                        pt.join()
                        lock = False
                if not MT and PT:
                        pt = ProxyThread(conn, addr, counter)
                        pt.start()
                        pt.join()                    


                
            except KeyboardInterrupt:
                print('\nKeyboardInterrupt')
                sock.close()
                sys.exit()
    except:
        # tb = traceback.format_exc()
        # print(tb)
        pass


if __name__ == '__main__':
    main()