# Fixture: data files

Technical fixture of the checker prototype. This is not a course lesson.

The program reads files from its working folder; `data=` copies a data folder into it.

<!-- run: read_files data=tests/checker/fixtures/data/readings -->

```cpp
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

int main() {
    std::string name;
    while (std::getline(std::cin, name)) {
        std::ifstream file{name};
        if (!file) {
            std::cout << name << ": cannot open\n";
            continue;
        }
        int count{0};
        int total{0};
        std::string line;
        while (std::getline(file, line)) {
            if (!line.empty() && line.back() == '\r') {
                line.pop_back();
            }
            if (line.empty()) {
                continue;
            }
            std::istringstream stream{line};
            int value{0};
            if (stream >> value) {
                total += value;
                ++count;
            }
        }
        std::cout << name << ": " << count << " value(s), total " << total << "\n";
    }
}
```

An ordinary file and an empty file.

<!-- input: read_files -->

```text
readings.txt
empty.txt
```

<!-- output: read_files -->

```text
readings.txt: 3 value(s), total 50
empty.txt: 0 value(s), total 0
```

A file with CRLF line ends and a missing file.

<!-- input: read_files -->

```text
crlf.txt
missing.txt
```

<!-- output: read_files -->

```text
crlf.txt: 2 value(s), total 12
missing.txt: cannot open
```

The program changes its data file; every run gets a fresh copy and the original stays unchanged.

<!-- run: update_counter data=tests/checker/fixtures/data/counter -->

```cpp
#include <fstream>
#include <iostream>

int main() {
    int count{0};
    {
        std::ifstream in{"counter.txt"};
        in >> count;
    }
    ++count;
    std::ofstream out{"counter.txt"};
    out << count << "\n";
    std::cout << "count: " << count << "\n";
}
```

<!-- output: update_counter -->

```text
count: 2
```

<!-- output: update_counter -->

```text
count: 2
```
