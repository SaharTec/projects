#include "InventoryManager.h"
#include <sstream>
using namespace std;

// Initialize the list of items
InventoryManager::InventoryManager(){
    items.emplace_back(1, "Camera");
    items.emplace_back(2, "Tripod");
    items.emplace_back(3, "Laptop");
    items.emplace_back(4, "Projector");
    items.emplace_back(5, "Microphone");
    items.emplace_back(6, "Speaker");
    items.emplace_back(7, "HDMI_Cable");
    items.emplace_back(8, "Ethernet_Cable");
    items.emplace_back(9, "Keyboard");
    items.emplace_back(10, "Mouse");
    items.emplace_back(11, "Monitor");
    items.emplace_back(12, "USB_Hub");
    items.emplace_back(13, "Power_Bank");
    items.emplace_back(14, "Router");
    items.emplace_back(15, "VR_Headset");
}

Item& InventoryManager::findItemById(int itemId){
    for(auto& item : items ){
        if(item.getId() == itemId){
            return item;
        }
    }
    throw runtime_error("Item not found");
}

string InventoryManager::listItems(){
    // lock the mutex so other client cant borrow/return items while we are reading the list.
    lock_guard<mutex> lock(mtx);
    ostringstream oss;
    oss << "OK LIST " << items.size() << "\n";

    for(const auto& item: items){
        oss << item.toString() << "\n";
    }
    return oss.str();  //lock automatically releases here
}

void InventoryManager::borrowItem(int itemId, const string& username){
    lock_guard<mutex> lock(mtx); // lock to prevent 2 clint to borrow the same item at the same time
    Item& item = findItemById(itemId);

    if (!item.isAvailable()) {
        throw runtime_error("already borrowed by " + item.getBorrower());
    }

    item.borrow(username);  //checking "isBorrowed" is inside item.borrow()
}

void InventoryManager::returnItem(int itemId, const string& username){
    lock_guard<mutex> lock(mtx);
    Item& item = findItemById(itemId);

    item.returnBack(username);

    cv.notify_all(); //if some client waiting for an item this wakes them up to check if the item they want is free.
}

void InventoryManager::waitUntilAvailable(int itemId, const string& username){
    unique_lock<mutex> lock(mtx);
    Item& item = findItemById(itemId);
    // prevent the clients for wait for an item they are holding.
    if(!item.isAvailable() && item.getBorrower() == username){
        throw runtime_error("Deadlock: user is waiting for their own item");
    }
    cv.wait(lock, [&item](){
        return item.isAvailable();
    });

}