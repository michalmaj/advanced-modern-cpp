# Fixture: projekt z danymi

Techniczny fixture prototypu checkera. To nie jest lekcja kursu. Projekt CMake bez CTest.

Program projektu czyta pliki z folderu danych projektu.

<!-- project: readings_demo dir=tests/checker/fixtures/projects/spike_readings mode=run target=readings_app data=tests/checker/fixtures/projects/spike_readings/data -->

<!-- input: readings_demo -->

```text
readings.txt
crlf.txt
missing.txt
```

<!-- output: readings_demo -->

```text
readings.txt: 3 value(s), total 15
crlf.txt: 2 value(s), total 3
missing.txt: cannot open
```

Program kontrolny projektu korzysta z tych samych danych.

<!-- project: readings_checks dir=tests/checker/fixtures/projects/spike_readings mode=test target=readings_checks data=tests/checker/fixtures/projects/spike_readings/data -->
