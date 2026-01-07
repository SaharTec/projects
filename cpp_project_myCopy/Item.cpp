#include "Item.h"
#include <stdexcept>
#include <sstream>

using namespace std;

Item::Item(int id,const string& name): id(id), name(name), isBorrowed(false), borrowedBy(""){}

//return refrens of the id of the item
int Item::getId() const{
    return id;
}


//return the name of the item
string& Item::getName() {
    return name;
}


//check if the item is available.
bool Item::isAvailable() const{
    return !isBorrowed;
}


//return refrens of the name of the person who borrowed the item
string& Item::getBorrower() {
    return borrowedBy;
}


//borrowed the item to the user
void Item::borrow(const string& username){
    if(username.empty()){   //check for empty username
        throw runtime_error("username filld can be empty");
    }
    if(isBorrowed){         //check if the item is alredy borrowed
        throw runtime_error("this item is already borrowed");
    }
    //update the item as borrowed
    isBorrowed = true;
    borrowedBy = username;
}


//return the borrowed item
void Item::returnBack(const string& username){
    if(username.empty()){       //check for empty username
        throw runtime_error("username filld can be empty!");
    }

    if(!isBorrowed){        //check if the item is't alredy borrowed
        throw runtime_error("this item is't borrowed!");
    }

    if(borrowedBy != username){   //check if other person tring to return the item
        throw runtime_error("username have to be the same as the one who borrowed");
    }
    //update the item to be availeble
    isBorrowed = false;
    borrowedBy = "";
}


//return visual string of the items status
string Item::toString() const{
    string result = to_string(id) + " " + name + " " ;
    
    if(isBorrowed){
        result += "BORROWED by= " + borrowedBy;
    }
    else{
        result += "FREE";
    }

    return result;
}