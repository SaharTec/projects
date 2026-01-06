#ifndef ITEM_H
#define ITEM_H
#include <string>
using namespace std;

class Item
{
private:
    int id;             // user id
    string name;        // the name of the item (camera, Laptop...)
    bool isBorrowed;    // return if the the item is alredy borrowed
    string borrowedBy;  // the name of the user that borrowd the item

public:
    Item(int id, const string& name);
    int getId() const;              //get the id code of the item
    string& getName() ;             //get the name of the item
    bool isAvailable() const;       //get if the item is available
    string& getBorrower() ;         //return the name of the borrowed name(if the item is't avalibale)

    void borrow(const string& username);
    /**
     * borrowed the item for the user if the item is not borrowed alrady but if the item is alredy borrowed
     * or if the username is not valid it will trow exeption for each scenario
     */

    void returnBack(const string& username);
    /**
     * return back the borrowed item and update the borrowed list so other user will be able to borrowed it
     * if the item is't borrowed or diffrent user try to return the item it will trow exeption for each scenario
     */

    string toString() const;
};  

#endif
