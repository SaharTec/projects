#include <iostream>
#include <string>
#include <cstring>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
using namespace std;

// Read from the socket one char at a time until he get a new line
string recvLine(int sockfd) {
    string line;
    char c;
    while (true) {
        int n = recv(sockfd, &c, 1, 0);
        if (n <= 0) {
            return ""; 
        }
        if (c == '\n') {
            break;
        }
        line += c;
    }
    return line;
}

// Send the data eith the needed new line character
bool sendLine(int sockfd, const string& line) {
    string msg = line + "\n";
    int sent = send(sockfd, msg.c_str(), msg.length(), 0);
    return sent > 0;
}


int parsePort(const string& portStr) {
    try {
        int port = stoi(portStr);
        if (port <= 0 || port > 65535) {
            return -1;
        }
        return port;
    } catch (...) {
        return -1;
    }
}

int main(int argc, char* argv[]) {
    if (argc != 3) {
        cerr << "Usage: " << argv[0] << " <server_ip> <server_port>" << std::endl;
        return 1;
    }

    string serverIp = argv[1];
    int port = parsePort(argv[2]);
    
    if (port == -1) {
        cerr << "Error: Invalid port number" << endl;
        return 1;
    }

    // create socket
    int sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) {
        cerr << "Error: Failed to create socket" << endl;
        return 1;
    }

    // settenig for server
    struct sockaddr_in serverAddr;
    memset(&serverAddr, 0, sizeof(serverAddr));
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(port);

    if (inet_pton(AF_INET, serverIp.c_str(), &serverAddr.sin_addr) <= 0) {
        cerr << "Error: Invalid IP address" << endl;
        close(sockfd);
        return 1;
    }

    // connection to the server
    if (connect(sockfd, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) < 0) {
        cerr << "Error: Failed to connect to server" << endl;
        close(sockfd);
        return 1;
    }

    cout << "Connected to server at " << serverIp << ":" << port << endl;
    cout << "Type your commands (HELLO, LIST, BORROW, RETURN, WAIT, QUIT):" << endl;

    
    string userInput;
    while (true) {
        cout << "> ";
        
        // getting the commend from the user
        if (!getline(cin, userInput)) {
            break;
        }

        if (userInput.empty()) {
            continue;
        }

        // sending commend to the server
        if (!sendLine(sockfd, userInput)) {
            cerr << "Error: Failed to send command" << endl;
            break;
        }

        // reading answer from the server
        string response = recvLine(sockfd);
        if (response.empty()) {
            cout << "Disconnected from server" << endl;
            break;
        }

        // show the response
        cout << response << endl;

        // reading the lines of the LIST
        if (response.find("OK LIST") == 0) {
            // getting the number of the items
            size_t pos = response.find("LIST") + 5;
            int count = 0;
            try {
                count = stoi(response.substr(pos));
            } catch (...) {
                cerr << "Error: Invalid LIST response format" << endl;
                continue;
            }

            // reading all the items
            for (int i = 0; i < count; i++) {
                string itemLine = recvLine(sockfd);
                if (itemLine.empty()) {
                    cout << "Disconnected from server" << endl;
                    close(sockfd);
                    return 0;
                }
                cout << itemLine << endl;
            }
        }

        
        if (userInput == "QUIT" || response.find("OK BYE") == 0) {
            break;
        }
    }

    // close the conection 
    close(sockfd);
    cout << "Connection closed" << endl;
    
    return 0;
}