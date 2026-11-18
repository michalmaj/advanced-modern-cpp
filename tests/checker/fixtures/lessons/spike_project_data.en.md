# Fixture: a project with data

Technical fixture of the checker prototype. This is not a course lesson. A CMake project without CTest.

The project's program reads files from the project's data folder.

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

The project's check program uses the same data.

<!-- project: readings_checks dir=tests/checker/fixtures/projects/spike_readings mode=test target=readings_checks data=tests/checker/fixtures/projects/spike_readings/data -->
