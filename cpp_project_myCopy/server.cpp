#include "InventoryManager.h"
#include <iostream>
#include <string>
#include <cstring>
#include <thread>
#include <vector>
#include <sstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

//call for one line at a time
string recv_line(int sockfd){
    string line;
    char c;
    while(true){
        ssize_t n = recv(sockfd, &c, 1, 0);
        if(n <= 0){
            return "";
        }
        if (c == '\n'){
            break;
        }
        line += c;
    }
    return line;
}

bool send_line(int sockfd, const string& line){
    string msg = line + "\n";
    int sent = send(sockfd, msg.c_str(), msg.length(),0);
    return sent > 0;
}

vector<string> split(const string& str){
    vector<string> tokens;
    istringstream iss(str);
    string token;
    while(iss >> token){
        tokens.push_back(token);
    }
    return tokens;
}

bool contains(const string& str, const string& substring) {
    return str.find(substring) != string::npos;
}

void handelClient(int clientSocket, InventoryManager& inventory){
    string username;
    bool authentication = false;

    while(true){
        string commend = recv_line(clientSocket);

        try{
            vector<string> tokens = split(commend);
            if(tokens.empty()){
                send_line(clientSocket, "ERR PROTOCOL command_invalid");
                continue;
            }
            string comm = tokens[0];
            if (comm == "HELLO"){

                if(tokens.size() < 2){
                    send_line(clientSocket, "ERR PROTOCOL missing_username");
                    continue;
                }

                username = tokens[1];

                if(username.empty()){
                    send_line(clientSocket, "ERR PROTOCOL missing_username");
                    continue;
                }

                authentication = true;
                send_line(clientSocket, "OK HELLO");
            }

            else if (!authentication){
                send_line(clientSocket, "ERR STATE not_authenticated");
            }

            else if (comm == "LIST"){
                string response = inventory.listItems();
                send(clientSocket, response.c_str(), response.length(), 0);
            }
            
            else if(comm == "BORROW"){
                if (tokens.size() < 2){
                    send_line(clientSocket, "ERR PROTOCOL invalid_id");
                    continue;
                }

                int itemId;

                try{
                    itemId = stoi(tokens[1]);
                }catch( ... ){
                    send_line(clientSocket, "ERR PROTOCOL invalid_id");
                    continue;
                }

                try{
                    inventory.borrowItem(itemId, username);
                    send_line(clientSocket, "OK BORROWED" + to_string(itemId));
                }
                catch( const exception& e){
                    string err_msg = e.what();
                    if(contains(err_msg, "not found")){
                        send_line(clientSocket, " ERR NOT_FOUNT item");
                        continue;
                    }
                    else if (contains(err_msg, "already borrowed")){
                        send_line(clientSocket, " ERR UNAVAILABLE borrowed_by=" + username);
                        continue;
                    }
                }
                
            }

            else if ( comm == "RETURN"){
                if (tokens.size() < 2){
                    send_line(clientSocket, "ERR PROTOCOL invalid_id");
                    continue;
                }

                int itemId;

                try{
                    itemId = stoi(tokens[1]);
                }catch( ... ){
                    send_line(clientSocket, "ERR PROTOCOL invalid_id");
                    continue;
                }

                try{
                    inventory.returnItem(itemId, username);
                    send_line(clientSocket, "OK RETURNED" + to_string(itemId));
                }
                catch( const exception& e){
                    string err_msg = e.what();
                    
                    if(contains(err_msg, "not found")){
                        send_line(clientSocket, " ERR NOT_FOUNT item");
                        continue;
                    }

                    else if (contains(err_msg, "not borrows") || contains(err_msg, "was not borrowed by")){
                        send_line(clientSocket, "ERR PERMISSION not_owner");
                        continue;
                    }
                }

            }

            else if (comm == "WAIT"){
               if (tokens.size() < 2){
                    send_line(clientSocket, "ERR PROTOCOL invalid_id");
                    continue;
                }

                int itemId;

                try{
                    itemId = stoi(tokens[1]);
                }catch( ... ){
                    send_line(clientSocket, "ERR PROTOCOL invalid_id");
                    continue;
                }
                
                try{
                    inventory.waitUntilAvailable(itemId, username);
                    send_line(clientSocket, "OK AVAILABLE " + to_string(itemId));
                }
                catch(const exception& e){
                    string err_msg = e.what();

                    if(contains(err_msg, "not found")){
                        send_line(clientSocket, "ERR NOT_FOUNT item");
                        continue;
                    }

                    else if(contains(err_msg, "Deadlock")){
                        send_line(clientSocket, "ERR DEADLOCK item");
                    }
                }
            }

            else if (comm == "QUIT") {
                send_line(clientSocket, "OK BYE");
                break;
            }
            
            else {
                send_line(clientSocket, "ERR PROTOCOL invalid_command");
            }
        }catch(...){
            return ;
        }
    }
    close(clientSocket);
}

int main(int argc, char* argv[]){
    int port = 5555;
    try{
        if (port != 5555){
            throw exception();
        }
    }
    catch (...) {
        cerr << "Error: Invalid port number" << endl;
        return 1;
    }

    InventoryManager inventory;
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);

    int serverSock = socket(AF_INET, SOCK_STREAM, 0);
    if (serverSock < 0) {
        cerr << "Error: Failed to create socket" << endl;
        return 1;
    }

    int opt = 1;
    setsockopt(serverSock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    // Bind לפורט
    struct sockaddr_in serverAddr;
    memset(&serverAddr, 0, sizeof(serverAddr));
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_addr.s_addr = INADDR_ANY;
    serverAddr.sin_port = htons(port);

    if (bind(serverSock, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) < 0) {
        cerr << "Error: Failed to bind to port " << port << endl;
        close(serverSock);
        return 1;
    }

    if (listen(serverSock, 10) < 0) {
        cerr << "Error: Failed to listen" << endl;
        close(serverSock);
        return 1;
    }

    cout << "Server is running and listening on port " << port << endl;

    
    while (true) {
        struct sockaddr_in clientAddr;
        socklen_t clientLen = sizeof(clientAddr);
        
        int clientSock = accept(serverSock, (struct sockaddr*)&clientAddr, &clientLen);
        if (clientSock < 0) {
            cerr << "Error: Failed to accept client" << endl;
            continue;
        }

        
        thread clientThread(handelClient, clientSock, ref(inventory));
        clientThread.detach();  
    }

    close(serverSock);
    return 0;
}