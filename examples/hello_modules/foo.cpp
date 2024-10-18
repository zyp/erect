module;

#include <iostream>

export module foo;

export void foo() {
    std::cout << "Hello from module foo!" << std::endl;
}
