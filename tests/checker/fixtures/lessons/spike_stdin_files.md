# Fixture: wejscie z pliku

Techniczny fixture prototypu checkera. To nie jest lekcja kursu.

Jeden program, kilka przypadków kontrolnych.

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

Przypadek 1: dane w lekcji.

<!-- input: sum_numbers -->

```text
1 2 3
```

<!-- output: sum_numbers -->

```text
3 number(s), total 6
```

Przypadek 2: dane z pliku (`in=`).

<!-- output: sum_numbers in=tests/checker/fixtures/data/stdin/numbers.txt -->

```text
4 number(s), total 100
```

Przypadek 3: pusty plik.

<!-- output: sum_numbers in=tests/checker/fixtures/data/stdin/empty.txt -->

```text
0 number(s), total 0
```
