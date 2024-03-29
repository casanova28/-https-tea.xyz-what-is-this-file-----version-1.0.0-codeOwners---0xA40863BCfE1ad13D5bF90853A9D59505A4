# =============================================================================
# Casanova Enricher Unit Tests
# =============================================================================
from typing import List

import csv
import gzip
import casanova
import pytest
import time
import sys
from io import StringIO
from dataclasses import dataclass
from collections import defaultdict
from quenouille import imap_unordered

from test.utils import collect_csv

from casanova.resumers import (
    LastCellComparisonResumer,
    RowCountResumer,
    IndexedResumer,
    BatchResumer,
)
from casanova.record import TabularRecord, tabular_field
from casanova.exceptions import Py310NullByteWriteError
from casanova.utils import PY_310, CsvIO


class TestEnricher(object):
    def test_exceptions(self, tmpdir):
        output_path = str(tmpdir.join("./wrong_resumer.csv"))

        with pytest.raises(TypeError):
            resumer = IndexedResumer(output_path)
            with open("./test/resources/people.csv") as f, resumer:
                casanova.enricher(f, resumer)

    def test_basics(self, tmpdir):
        output_path = str(tmpdir.join("./enriched.csv"))
        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, add=("line",))

            for i, row in enumerate(enricher):
                enricher.writerow(row, [i])

        assert collect_csv(output_path) == [
            ["name", "surname", "line"],
            ["John", "Matthews", "0"],
            ["Mary", "Sue", "1"],
            ["Julia", "Stone", "2"],
        ]

        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, add=("line", "salutation"))

            for i, row in enumerate(enricher):
                enricher.writerow(row, (i, "hey"))

        assert collect_csv(output_path) == [
            ["name", "surname", "line", "salutation"],
            ["John", "Matthews", "0", "hey"],
            ["Mary", "Sue", "1", "hey"],
            ["Julia", "Stone", "2", "hey"],
        ]

        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, add=("0", "1", "2"))

            for i, row in enumerate(enricher):
                enricher.writerow(row, (j for j in range(3)))

        assert collect_csv(output_path) == [
            ["name", "surname", "0", "1", "2"],
            ["John", "Matthews", "0", "1", "2"],
            ["Mary", "Sue", "0", "1", "2"],
            ["Julia", "Stone", "0", "1", "2"],
        ]

    def test_writebatch(self, tmpdir):
        output_path = str(tmpdir.join("./enriched.csv"))
        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, add=("number",))

            for row in enricher:
                enricher.writebatch(row, [[2], [3], [6]])
                break

        assert collect_csv(output_path) == [
            ["name", "surname", "number"],
            ["John", "Matthews", "2"],
            ["John", "Matthews", "3"],
            ["John", "Matthews", "6"],
        ]

    def test_dialect(self, tmpdir):
        output_path = str(tmpdir.join("./enriched.csv"))
        with open("./test/resources/semicolons.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, add=("line",), delimiter=";")

            for i, row in enumerate(enricher):
                enricher.writerow(row, [i])

        assert collect_csv(output_path) == [
            ["name", "surname", "line"],
            ["Rose", "Philips", "0"],
            ["Luke", "Atman", "1"],
        ]

    def test_gzip(self, tmpdir):
        output_path = str(tmpdir.join("./enriched.csv"))
        with gzip.open("./test/resources/people.csv.gz", "rt") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, add=("line",))

            for i, row in enumerate(enricher):
                enricher.writerow(row, [i])

        assert collect_csv(output_path) == [
            ["name", "surname", "line"],
            ["John", "Matthews", "0"],
            ["Mary", "Sue", "1"],
            ["Julia", "Stone", "2"],
        ]

    def test_select(self, tmpdir):
        output_path = str(tmpdir.join("./enriched_select.csv"))
        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, select=("name",), add=("line",))

            for i, row in enumerate(enricher):
                enricher.writerow(row, [i])

        assert collect_csv(output_path) == [
            ["name", "line"],
            ["John", "0"],
            ["Mary", "1"],
            ["Julia", "2"],
        ]

    def test_padding(self, tmpdir):
        output_path = str(tmpdir.join("./enriched_padding.csv"))
        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, select=("name",), add=("line",))

            for i, row in enumerate(enricher):
                enricher.writerow(row)

        assert collect_csv(output_path) == [
            ["name", "line"],
            ["John", ""],
            ["Mary", ""],
            ["Julia", ""],
        ]

    def test_resumable(self, tmpdir):
        log = defaultdict(list)

        def listener(name, row):
            log[name].append(list(row))

        output_path = str(tmpdir.join("./enriched_resumable.csv"))

        resumer = RowCountResumer(output_path, listener=listener)

        with open("./test/resources/people.csv") as f, resumer:
            enricher = casanova.enricher(f, resumer, add=("x2",), select=("name",))

            row = next(iter(enricher))
            enricher.writerow(row, [2])

        assert collect_csv(output_path) == [["name", "x2"], ["John", "2"]]

        with open("./test/resources/people.csv") as f, resumer:
            enricher = casanova.enricher(f, resumer, add=("x2",), select=("name",))

            for i, row in enumerate(enricher):
                enricher.writerow(row, [(i + 2) * 2])

        assert collect_csv(output_path) == [
            ["name", "x2"],
            ["John", "2"],
            ["Mary", "4"],
            ["Julia", "6"],
        ]

        assert log == {
            "output.row.read": [["John", "2"]],
            "input.row.filter": [["John", "Matthews"]],
        }

    def test_resumable_last_cell_comparison(self, tmpdir):
        log = defaultdict(list)

        def listener(name, row):
            log[name].append(list(row))

        output_path = str(tmpdir.join("./enriched_resumable.csv"))

        resumer = LastCellComparisonResumer(
            output_path, value_column=0, listener=listener
        )

        with open("./test/resources/people.csv") as f, resumer:
            enricher = casanova.enricher(f, resumer, add=("x2",), select=("name",))

            row = next(iter(enricher))
            enricher.writerow(row, [2])

        assert collect_csv(output_path) == [["name", "x2"], ["John", "2"]]

        with open("./test/resources/people.csv") as f, resumer:
            enricher = casanova.enricher(f, resumer, add=("x2",), select=("name",))

            for i, row in enumerate(enricher):
                enricher.writerow(row, [(i + 2) * 2])

        assert collect_csv(output_path) == [
            ["name", "x2"],
            ["John", "2"],
            ["Mary", "4"],
            ["Julia", "6"],
        ]

        assert log == {"input.row.filter": [["John", "Matthews"]]}

    def test_indexed(self, tmpdir):
        def job(payload):
            i, row = payload
            s = int(row[2])
            time.sleep(s * 0.01)

            return i, row

        output_path = str(tmpdir.join("./enriched_resumable_indexed.csv"))
        with open("./test/resources/people_unordered.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.indexed_enricher(f, of, add=("x2",), select=("name",))

            for i, row in imap_unordered(enricher, job, 3):
                enricher.writerow(i, row, [(i + 1) * 2])

        def sort_output(o):
            return sorted(tuple(i) for i in o)

        assert sort_output(collect_csv(output_path)) == sort_output(
            [
                ["name", "index", "x2"],
                ["Mary", "1", "4"],
                ["Julia", "2", "6"],
                ["John", "0", "2"],
            ]
        )

    def test_indexed_cells(self, tmpdir):
        output_path = str(tmpdir.join("./enriched_resumable_indexed.csv"))
        with open("./test/resources/people_unordered.csv") as f, open(
            output_path, "a+"
        ) as of:
            enricher = casanova.indexed_enricher(f, of, add=("x2",), select=("name",))

            names = [t for t in enricher.cells("name")]

        assert sorted(names) == sorted([(0, "John"), (1, "Mary"), (2, "Julia")])

        with open("./test/resources/people_unordered.csv") as f, open(
            output_path, "a+"
        ) as of:
            enricher = casanova.indexed_enricher(f, of, add=("x2",), select=("name",))

            names = [(i, v) for i, row, v in enricher.cells("name", with_rows=True)]

        assert names == [(0, "John"), (1, "Mary"), (2, "Julia")]

    def test_indexed_resumable(self, tmpdir):
        log = defaultdict(list)

        def listener(name, row):
            log[name].append(list(row))

        def job(payload):
            i, row = payload
            s = int(row[2])
            time.sleep(s * 0.1)

            return i, row

        output_path = str(tmpdir.join("./enriched_resumable_indexed.csv"))

        resumer = IndexedResumer(output_path, listener=listener)

        with open("./test/resources/people_unordered.csv") as f, resumer:
            enricher = casanova.indexed_enricher(
                f, resumer, add=("x2",), select=("name",)
            )

            for j, (i, row) in enumerate(imap_unordered(enricher, job, 3)):
                enricher.writerow(i, row, [(i + 1) * 2])

                if j == 1:
                    break

        def sort_output(o):
            return sorted(tuple(i) for i in o)

        assert sort_output(collect_csv(output_path)) == sort_output(
            [["name", "index", "x2"], ["Mary", "1", "4"], ["Julia", "2", "6"]]
        )

        with open("./test/resources/people_unordered.csv") as f, resumer:
            enricher = casanova.indexed_enricher(
                f, resumer, add=("x2",), select=("name",)
            )

            for j, (i, row) in enumerate(imap_unordered(enricher, job, 3)):
                enricher.writerow(i, row, [(i + 1) * 2])

        assert sort_output(collect_csv(output_path)) == sort_output(
            [
                ["name", "index", "x2"],
                ["Mary", "1", "4"],
                ["Julia", "2", "6"],
                ["John", "0", "2"],
            ]
        )

        assert sort_output(log["output.row.read"]) == sort_output(
            [["Mary", "1", "4"], ["Julia", "2", "6"]]
        )
        assert sort_output(log["input.row.filter"]) == sort_output(
            [["Mary", "Sue", "1"], ["Julia", "Stone", "2"]]
        )

    def test_indexed_resuming_soundness(self, tmpdir):
        output_path = str(tmpdir.join("./indexed_resuming_soundness.csv"))

        with open("./test/resources/more_people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.indexed_enricher(f, of)

            for index, row in enricher:
                enricher.writerow(index, row)

                if index >= 2:
                    break

        resumer = IndexedResumer(output_path)
        with casanova.indexed_enricher(
            "./test/resources/more_people.csv", resumer
        ) as enricher, resumer:
            for index, row in enricher:
                enricher.writerow(index, row)

        assert collect_csv(output_path) == [
            ["name", "index"],
            ["John", "0"],
            ["Lisa", "1"],
            ["Mary", "2"],
            ["Alexander", "3"],
            ["Gary", "4"],
        ]

    def test_stdout(self, capsys):
        sys.stdout.write("this,should,happen\n")
        with open("./test/resources/people.csv") as f:
            enricher = casanova.enricher(f, sys.stdout, add=("line",))

            for i, row in enumerate(enricher):
                enricher.writerow(row, [i])

        result = list(csv.reader(StringIO(capsys.readouterr().out)))

        assert result == [
            ["this", "should", "happen"],
            ["name", "surname", "line"],
            ["John", "Matthews", "0"],
            ["Mary", "Sue", "1"],
            ["Julia", "Stone", "2"],
        ]

    def test_combined_pos(self, tmpdir):
        output_path = str(tmpdir.join("./enriched.csv"))
        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.enricher(f, of, add=("line",), select=("surname",))

            assert len(enricher.output_headers) == 2
            assert enricher.output_headers.surname == 0
            assert enricher.output_headers.line == 1

    def test_batch_enricher(self, tmpdir):
        output_path = str(tmpdir.join("./enriched.csv"))
        with open("./test/resources/people.csv") as f, open(
            output_path, "w", newline=""
        ) as of:
            enricher = casanova.batch_enricher(
                f, of, add=("color",), select=("surname",)
            )

            for row in enricher:
                enricher.writebatch(row, [["blue"], ["red"]], cursor="next")
                enricher.writebatch(row, [["purple"], ["cyan"]])

        assert collect_csv(output_path) == [
            ["surname", "cursor", "color"],
            ["Matthews", "", "blue"],
            ["Matthews", "next", "red"],
            ["Matthews", "", "purple"],
            ["Matthews", "end", "cyan"],
            ["Sue", "", "blue"],
            ["Sue", "next", "red"],
            ["Sue", "", "purple"],
            ["Sue", "end", "cyan"],
            ["Stone", "", "blue"],
            ["Stone", "next", "red"],
            ["Stone", "", "purple"],
            ["Stone", "end", "cyan"],
        ]

    def test_strip_null_bytes_on_write(self):
        data = [["name"], ["John\0 Kawazaki"]]
        output = StringIO()

        enricher = casanova.enricher(data, output, strip_null_bytes_on_write=True)

        for row in enricher:
            enricher.writerow(row)

        result = output.getvalue().strip()

        assert "\0" not in result

    def test_py310_wrapper(self):
        if not PY_310:
            return

        data = [["name"], ["John\0 Kawazaki"]]

        with pytest.raises(Py310NullByteWriteError):
            enricher = casanova.enricher(data, StringIO())

            for row in enricher:
                enricher.writerow(row)

    def test_different_writer_dialect(self):
        data = CsvIO([["John", "Matthews"]], fieldnames=["name", "surname"])
        output = StringIO()

        enricher = casanova.enricher(
            data, output, writer_lineterminator="\n", writer_delimiter=";"
        )

        for row in enricher:
            enricher.writerow(row)

        assert output.getvalue().strip() == "name;surname\nJohn;Matthews"

    def test_input_duplicate_column_names(self):
        data = CsvIO(
            [["John", "Mary", "Matthews"]], fieldnames=["name", "name", "surname"]
        )
        output = StringIO()

        enricher = casanova.enricher(data, output, writer_lineterminator="\n")

        for row in enricher:
            enricher.writerow(row)

        assert output.getvalue().strip() == "name,name,surname\nJohn,Mary,Matthews"

    def test_prebuffer_bytes_and_resuming(self, tmpdir):
        output_path = str(tmpdir.join("./enriched_resumable.csv"))

        resumer = RowCountResumer(output_path)

        with open("./test/resources/people.csv") as f, resumer:
            enricher = casanova.enricher(
                f, resumer, add=("x2",), select=("name",), prebuffer_bytes=1024
            )
            row = next(iter(enricher))
            enricher.writerow(row, [2])

        assert collect_csv(output_path) == [["name", "x2"], ["John", "2"]]

        with open("./test/resources/people.csv") as f, resumer:
            enricher = casanova.enricher(
                f, resumer, add=("x2",), select=("name",), prebuffer_bytes=1024
            )

            for i, row in enumerate(enricher):
                enricher.writerow(row, [(i + 2) * 2])

        assert collect_csv(output_path) == [
            ["name", "x2"],
            ["John", "2"],
            ["Mary", "4"],
            ["Julia", "6"],
        ]

    def test_no_headers(self):
        with open("./test/resources/no_headers.csv") as f:
            with pytest.raises(TypeError, match="no_headers"):
                casanova.enricher(f, StringIO(), add=("test",), no_headers=True)

        with open("./test/resources/no_headers.csv") as f:
            buf = StringIO()

            enricher = casanova.enricher(
                f, buf, writer_lineterminator="\n", add=1, no_headers=True
            )

            with pytest.raises(TypeError):
                enricher.writerow(["John", "Martin"], [1, 2])

            for i, row in enumerate(enricher):
                enricher.writerow(row, [i])

            assert collect_csv(buf) == [
                ["John", "Matthews", "0"],
                ["Mary", "Sue", "1"],
                ["Julia", "Stone", "2"],
            ]

        with open("./test/resources/no_headers.csv") as f:
            buf = StringIO()

            enricher = casanova.enricher(
                f, buf, writer_lineterminator="\n", select="1", add=1, no_headers=True
            )

            for i, row in enumerate(enricher):
                enricher.writerow(row, [i])

            assert collect_csv(buf) == [
                ["John", "0"],
                ["Mary", "1"],
                ["Julia", "2"],
            ]

    def test_write_tabular_record(self):
        @dataclass
        class Video(TabularRecord):
            title: str
            tags: List[str] = tabular_field(plural_separator="&")

        buf = StringIO()

        enricher = casanova.enricher(
            CsvIO([["John"]], ["name"]),
            buf,
            add=Video,
            writer_lineterminator="\n",
        )

        for row in enricher:
            enricher.writerow(row, Video("Title", ["a", "b"]))

        assert buf.getvalue().strip() == "name,title,tags\nJohn,Title,a&b"

    def test_indexed_writerow_without_addendum(self):
        buf = StringIO()

        enricher = casanova.indexed_enricher(
            CsvIO([["John"]], ["name"]), buf, add=["count"], writer_lineterminator="\n"
        )

        for index, row in enricher:
            enricher.writerow(index, row)

        assert buf.getvalue().strip() == "name,index,count\nJohn,0,"

    def test_variadic_writerow(self):
        buf = StringIO()

        enricher = casanova.enricher(
            CsvIO([["John"]], ["name"]),
            buf,
            writer_lineterminator="\n",
            add=["count1", "count2"],
        )

        for row in enricher:
            enricher.writerow(row, [0], [1])

            with pytest.raises(TypeError):
                enricher.writerow(row, [1])

        assert buf.getvalue().strip() == "name,count1,count2\nJohn,0,1"

    def test_backwards_compatibility_writerow(self):
        # without add
        buf = StringIO()

        enricher = casanova.enricher(
            CsvIO([["John"]], ["name"]), buf, writer_lineterminator="\n"
        )

        for row in enricher:
            enricher.writerow(row, None)

        assert buf.getvalue().strip() == "name\nJohn"

        # with add
        buf = StringIO()

        enricher = casanova.enricher(
            CsvIO([["John"]], ["name"]), buf, add=["count"], writer_lineterminator="\n"
        )

        for row in enricher:
            enricher.writerow(row, None)

        assert buf.getvalue().strip() == "name,count\nJohn,"

        # indexed
        buf = StringIO()

        enricher = casanova.indexed_enricher(
            CsvIO([["John"]], ["name"]), buf, add=["count"], writer_lineterminator="\n"
        )

        for index, row in enricher:
            enricher.writerow(index, row, None)

        assert buf.getvalue().strip() == "name,index,count\nJohn,0,"

    def test_batch_enricher_resumer(self, tmpdir):
        output_path = str(tmpdir.join("./batch_enricher_resumer.csv"))

        with open(output_path, "w") as f:
            f.write("name,cursor\njohn,,")

        # NOTE: this should not raise, as per issue #123
        with BatchResumer(output_path, value_column="name") as resumer:
            casanova.batch_enricher(StringIO("name\njohn\nmary"), resumer)

    def test_input_fieldnames_validity(self):
        enricher = casanova.enricher(
            StringIO("name,surname\njohn,mary"),
            StringIO(),
            add=("age",),
        )

        assert enricher.fieldnames == ["name", "surname"]
        assert enricher.output_fieldnames == ["name", "surname", "age"]

        enricher = casanova.enricher(
            StringIO("name,surname\njohn,mary"),
            StringIO(),
            add=("age",),
            select=("name",),
        )

        assert enricher.fieldnames == ["name", "surname"]
        assert enricher.output_fieldnames == ["name", "age"]
