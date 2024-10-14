import pytsk3
import sqlite3

def isTrue():
    return "Hello World"

def main():
    userInput = input("Enter T or F\n")
    if userInput == "T":
        return isTrue()
    return "Not T"

if __name__ == "__main__":
    print(main())