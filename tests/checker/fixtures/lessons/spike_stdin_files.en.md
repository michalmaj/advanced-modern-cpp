# Fixture: input from a file

Technical fixture of the checker prototype. This is not a course lesson.

One program, several control cases.

<!-- run: sum_numbers -->

```cpp
#include <iostream>

int main() {
    long long total{0};
    int count{0};
    int value{0};
    while (std::cin >> value) {
        total += value;
        ++count;
    }
    std::cout << count << " number(s), total " << total << "\n";
}
```

Case 1: data in the lesson.

<!-- input: sum_numbers -->

```text
1 2 3
```

<!-- output: sum_numbers -->

```text
3 number(s), total 6
```

Case 2: data from a file (`in=`).

<!-- output: sum_numbers in=tests/checker/fixtures/data/stdin/numbers.txt -->

```text
4 number(s), total 100
```

Case 3: an empty file.

<!-- output: sum_numbers in=tests/checker/fixtures/data/stdin/empty.txt -->

```text
0 number(s), total 0
```
