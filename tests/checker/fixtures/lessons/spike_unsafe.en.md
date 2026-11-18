# Fixture: unsafe code for analysis only

Technical fixture of the checker prototype. This is not a course lesson.

Returning a reference to a local variable. Only compilation is checked.

<!-- compile_unsafe: dangling_return allow=-Wreturn-stack-address@3 -->

```cpp
const int& pick_local() {
    int local{42};
    return local;
}

int main() {
    return 0;
}
```

A view of a temporary object.

<!-- compile_unsafe: view_of_temporary allow=-Wdangling-gsl@5 -->

```cpp
#include <string>
#include <string_view>

int main() {
    std::string_view view = std::string("temporary text");
    return view.empty() ? 1 : 0;
}
```

Sentinel: running it would leave a file. After the check, the file must not exist.

<!-- compile_unsafe: sentinel_program -->

```cpp
#include <fstream>

int main() {
    std::ofstream trace{"SENTINEL-compile_unsafe-was-executed.txt"};
    trace << "this program must never be run by the checker\n";
}
```
