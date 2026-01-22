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
#include <fstream>
#include <atomic>
using namespace std;

atomic<bool> g_running(true);
/**
 * Log all the activity of the server to a txt file
 */
void logMessage(const string& msg){

    ofstream logFile("server_log.txt" , ios::app);
    if(logFile.is_open()){
        logFile << msg << endl;
        logFile.close();
    }else {
        cerr << "Error: Unable to write to log file!" << endl;
    }
}

// Read from the socket one char at a time until he get a new line
string recv_line(int sockfd){
    string line;
    char c;
    while(true){
        ssize_t n = recv(sockfd, &c, 1, 0);
        if(n <= 0){
            return "";
        }
        if (c == '\n'){
            break;  //end of a message found
        }
        line += c;
    }
    return line;
}
// Send the data eith the needed new line character
bool send_line(int sockfd, const string& line){
    string msg = line + "\n";
    int sent = send(sockfd, msg.c_str(), msg.length(),0);
    return sent > 0;
}

// Splite the commend string ("HELLO BOB" --> ["HELLO", "BOB"])
vector<string> split(const string& str){
    vector<string> tokens;
    istringstream iss(str);
    string token;
    while(iss >> token){
        tokens.push_back(token);
    }
    return tokens;
}
//check for error messages
bool contains(const string& str, const string& substring) {
    return str.find(substring) != string::npos;
}

/**
 * Main client handling loop. This runs in a SEPARATE THREAD for every user.
 * this is where the protocol (HELLO, BORROW ...) is actually processed.
 */
void handelClient(int clientSocket, InventoryManager& inventory){
    string username;
    bool authentication = false; //prevent from the client to do action before saying hello 

    while(true){
        string commend = recv_line(clientSocket); //wait for the client to send a commend/data

        try{
            vector<string> tokens = split(commend);
            if(tokens.empty()){
                send_line(clientSocket, "ERR PROTOCOL command_invalid");
                continue;
            }
            string comm = tokens[0];
            // --Authentication level--
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
                logMessage(username + " log in");
            }

            // Block all other commands if not logged in
            else if (!authentication){
                send_line(clientSocket, "ERR STATE not_authenticated");
            }

            // --Main commands--
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

                try{   //throw an exception if item is taken
                    inventory.borrowItem(itemId, username);
                    send_line(clientSocket, "OK BORROWED" + to_string(itemId));
                    logMessage(username + " borrowed item: " + to_string(itemId));
                }
                catch( const exception& e){
                    string err_msg = e.what();
                    if(contains(err_msg, "not found")){
                        send_line(clientSocket, " ERR NOT_FOUND item");
                        continue;
                    }
                    else if (contains(err_msg, "already borrowed")){
                        string owner = err_msg.substr(20);
                        send_line(clientSocket, " ERR UNAVAILABLE borrowed_by= " + owner);
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
                    logMessage(username + " return item: " + to_string(itemId));
                }
                catch( const exception& e){
                    string err_msg = e.what();
                    
                    if(contains(err_msg, "not found")){
                        send_line(clientSocket, " ERR NOT_FOUND item");
                        continue;
                    }

                    else if (contains(err_msg, "not borrows") || contains(err_msg, "was not borrowed by")){
                        send_line(clientSocket, "ERR PERMISSION not_owner");
                        continue;
                    }
                    else {
                        send_line(clientSocket, "ERR SERVER " + err_msg);
                    }
                }

            }

            else if (comm == "WAIT"){
                // It pauses this thread until the item returns.
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
                    //stop the waiting for the item (the item is free again)
                    send_line(clientSocket, "OK AVAILABLE " + to_string(itemId));
                    logMessage(username + " finished waiting for item " + to_string(itemId));
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
                logMessage(username + " disconnected");
                break;
            }
            
            else {
                send_line(clientSocket, "ERR PROTOCOL invalid_command");
            }
        }catch(...){
            return ;
        }
    }
    close(clientSocket);  // close the socket when the thread ends
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
    serverAddr.sin_addr.s_addr = INADDR_ANY; //Listen on all network interfaces
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

    
    while (true) {  //Main loop accepts new connections
        struct sockaddr_in clientAddr;
        socklen_t clientLen = sizeof(clientAddr);
        
        int clientSock = accept(serverSock, (struct sockaddr*)&clientAddr, &clientLen);
        if (clientSock < 0) {
            cerr << "Error: Failed to accept client" << endl;
            continue;
        }

        // Create a detached thread so main loop can go back to accepting new people immediately
        thread clientThread(handelClient, clientSock, ref(inventory));
        clientThread.detach();  
    }

    close(serverSock);
    return 0;
}