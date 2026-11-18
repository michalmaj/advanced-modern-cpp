# content_failure

A deliberately wrong expected output.

<!-- run: greeting -->

```cpp
#include <iostream>

int main() {
    std::cout << "hello\n";
}
```

<!-- output: greeting -->

```text
goodbye
```
