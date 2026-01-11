#include <iostream>
#include <string>
#include <cstring>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

// פונקציה לקריאת שורה אחת מה-socket
std::string recvLine(int sockfd) {
    std::string line;
    char c;
    while (true) {
        int n = recv(sockfd, &c, 1, 0);
        if (n <= 0) {
            return "";  // שגיאה או ניתוק
        }
        if (c == '\n') {
            break;
        }
        line += c;
    }
    return line;
}

// פונקציה לשליחת שורה (מוסיפה \n אוטומטית)
bool sendLine(int sockfd, const std::string& line) {
    std::string msg = line + "\n";
    int sent = send(sockfd, msg.c_str(), msg.length(), 0);
    return sent > 0;
}

// המרה בטוחה של port למספר
int parsePort(const std::string& portStr) {
    try {
        int port = std::stoi(portStr);
        if (port <= 0 || port > 65535) {
            return -1;
        }
        return port;
    } catch (...) {
        return -1;
    }
}

int main(int argc, char* argv[]) {
    // בדיקת פרמטרים
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <server_ip> <server_port>" << std::endl;
        return 1;
    }

    std::string serverIp = argv[1];
    int port = parsePort(argv[2]);
    
    if (port == -1) {
        std::cerr << "Error: Invalid port number" << std::endl;
        return 1;
    }

    // יצירת socket
    int sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd < 0) {
        std::cerr << "Error: Failed to create socket" << std::endl;
        return 1;
    }

    // הגדרת כתובת השרת
    struct sockaddr_in serverAddr;
    memset(&serverAddr, 0, sizeof(serverAddr));
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(port);

    if (inet_pton(AF_INET, serverIp.c_str(), &serverAddr.sin_addr) <= 0) {
        std::cerr << "Error: Invalid IP address" << std::endl;
        close(sockfd);
        return 1;
    }

    // התחברות לשרת
    if (connect(sockfd, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) < 0) {
        std::cerr << "Error: Failed to connect to server" << std::endl;
        close(sockfd);
        return 1;
    }

    std::cout << "Connected to server at " << serverIp << ":" << port << std::endl;
    std::cout << "Type your commands (HELLO, LIST, BORROW, RETURN, WAIT, QUIT):" << std::endl;

    // לולאה אינטראקטיבית
    std::string userInput;
    while (true) {
        std::cout << "> ";
        
        // קריאת פקודה מהמשתמש
        if (!std::getline(std::cin, userInput)) {
            break;  // EOF או שגיאה
        }

        if (userInput.empty()) {
            continue;
        }

        // שליחת הפקודה לשרת
        if (!sendLine(sockfd, userInput)) {
            std::cerr << "Error: Failed to send command" << std::endl;
            break;
        }

        // קריאת תשובה מהשרת
        std::string response = recvLine(sockfd);
        if (response.empty()) {
            std::cout << "Disconnected from server" << std::endl;
            break;
        }

        // הצגת התשוב
        std::cout << response << std::endl;

        // טיפול מיוחד ב-LIST - צריך לקרוא שורות נוספות1
        if (response.find("OK LIST") == 0) {
            // חילוץ מספר הפריטים
            size_t pos = response.find("LIST") + 5;
            int count = 0;
            try {
                count = std::stoi(response.substr(pos));
            } catch (...) {
                std::cerr << "Error: Invalid LIST response format" << std::endl;
                continue;
            }

            // קריאת כל הפריטים
            for (int i = 0; i < count; i++) {
                std::string itemLine = recvLine(sockfd);
                if (itemLine.empty()) {
                    std::cout << "Disconnected from server" << std::endl;
                    close(sockfd);
                    return 0;
                }
                std::cout << itemLine << std::endl;
            }
        }

        // בדיקה אם זה QUIT
        if (userInput == "QUIT" || response.find("OK BYE") == 0) {
            break;
        }
    }

    // סגירת החיבור
    close(sockfd);
    std::cout << "Connection closed" << std::endl;
    
    return 0;
}