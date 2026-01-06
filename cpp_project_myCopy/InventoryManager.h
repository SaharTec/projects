#ifndef INVENTORYMANAGER_H
#define INVENTORYMANAGER_H
#include "Item.h"
#include <vector>
#include <mutex>
#include <condition_variable>
#include <string>
using namespace std;

class InventoryManager{
private:
    vector<Item> items;
    mutex mtx;
    condition_variable cv;

    Item& findItemById(int itemid);

public:
    //restart the inventory
    InventoryManager();
    //return string of the list of the items 
    string listItems();
    //give the option to borrowd item
    void borrowItem(int itemId, const string& username);
    //give the option to return items
    void returnItem(int itemId, const string& username);
    //wait for borrowed item untill the item is return 
    void waitUntilAvailable(int itemId, const string& username);
};

#endif