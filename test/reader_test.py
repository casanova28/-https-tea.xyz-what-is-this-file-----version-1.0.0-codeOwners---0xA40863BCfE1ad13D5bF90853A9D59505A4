# =============================================================================
# Casanova Reader Unit Tests
# =============================================================================
import gzip
import casanova
import pytest
from io import StringIO
from dataclasses import dataclass

from casanova.defaults import set_defaults
from casanova.headers import RowWrapper, Headers
from casanova.reader import Multiplexer
from casanova.record import TabularRecord
from casanova.exceptions import (
    MissingColumnError,
    LtPy311ByteReadError,
    UnknownNamedColumnError,
)
from casanova.utils import LT_PY311, CsvIO


class TestReader(object):
    def test_exceptions(self):
        with pytest.raises(TypeError):
            casanova.reader(StringIO("name\nYomgui"), prebuffer_bytes=4.5)

        with pytest.raises(TypeError):
            casanova.reader(StringIO("name\nYomgui"), prebuffer_bytes=-456)

        with pytest.raises(MissingColumnError):
            casanova.reader(
                StringIO("name\nYomgui"), multiplex=Multiplexer("surname", "test")
            )

    def test_headers_positions(self):
        headers = Headers(["name", "surname"])

        assert len(headers) == 2
        assert list(headers) == ["name", "surname"]

        headers = Headers.rename(headers, "name", "first_name")

        assert list(headers) == ["first_name", "surname"]

    def test_empty_file(self):
        reader = casanova.reader(StringIO())

        assert reader.empty
        assert reader.headers == None
        assert list(reader) == []

        reader = casanova.reader(StringIO("name"))

        assert reader.empty
        assert reader.headers == Headers(["name"])
        assert list(reader) == []

        reader = casanova.reader(StringIO("name\nJohn"))

        assert not reader.empty

    def test_basics(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            assert reader.row_len == 2
            assert reader.headers is not None

            assert reader.headers.name == 0
            assert reader.headers.surname == 1

            assert "name" in reader.headers
            assert "whatever" not in reader.headers

            assert reader.headers["name"] == 0
            assert reader.headers["surname"] == 1

            assert reader.headers.get("name") == 0
            assert reader.headers.get("whatever") is None
            assert reader.headers.get("whatever", 1) == 1

            assert len(reader.headers) == 2
            assert reader.fieldnames == ["name", "surname"]

            with pytest.raises(UnknownNamedColumnError):
                reader.headers["whatever"]

            surnames = [row[reader.headers.surname] for row in reader]
            assert surnames == ["Matthews", "Sue", "Stone"]

    def test_dialect(self):
        with open("./test/resources/semicolons.csv") as f:
            reader = casanova.reader(f, delimiter=";")

            assert [row[0] for row in reader] == ["Rose", "Luke"]

    def test_cells(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            with pytest.raises(MissingColumnError):
                reader.cells("whatever")

            names = [name for name in reader.cells("name")]

            assert names == ["John", "Mary", "Julia"]

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            names = [
                (row[1], name) for row, name in reader.cells("name", with_rows=True)
            ]

            assert names == [("Matthews", "John"), ("Sue", "Mary"), ("Stone", "Julia")]

    def test_records(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            names = list(reader.records("name"))

            assert names == ["John", "Mary", "Julia"]

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            people = list(reader.records("surname", "name"))

            assert people == [("Matthews", "John"), ("Sue", "Mary"), ("Stone", "Julia")]

    def test_tabular_records_records(self):
        @dataclass
        class People(TabularRecord):
            name: str
            age: int

        data = CsvIO([["Mary", "45"]], fieldnames=["name", "age"])

        reader = casanova.reader(data)

        records = list(reader.records(People))

        assert records == [People("Mary", 45)]

        with open("./test/resources/people_unordered.csv") as f:
            reader = casanova.reader(f)

            with pytest.raises(TypeError):
                reader.records(People)

            reader.records(People, ignore_headers=True)

    def test_enumerate(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            indices = [i for i, _ in reader.enumerate()]

            assert indices == list(range(3))

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            indices = [i for i, _ in reader.enumerate(10)]

            assert indices == list(range(10, 13))

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            items = list(reader.enumerate_cells("name", 10))

            assert items == [(10, "John"), (11, "Mary"), (12, "Julia")]

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            items = list(reader.enumerate_cells("name", 10, with_rows=True))

            assert items == [
                (10, ["John", "Matthews"], "John"),
                (11, ["Mary", "Sue"], "Mary"),
                (12, ["Julia", "Stone"], "Julia"),
            ]

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            items = list(reader.enumerate_records("name", start=10, with_rows=True))

            assert items == [
                (10, ["John", "Matthews"], "John"),
                (11, ["Mary", "Sue"], "Mary"),
                (12, ["Julia", "Stone"], "Julia"),
            ]

    def test_no_headers(self):
        with open("./test/resources/no_headers.csv") as f:
            reader = casanova.reader(f, no_headers=True)

            assert reader.fieldnames is None

            surnames = [row[1] for row in reader]
            assert surnames == ["Matthews", "Sue", "Stone"]

    def test_cells_no_headers(self):
        with open("./test/resources/no_headers.csv") as f:
            reader = casanova.reader(f, no_headers=True)

            with pytest.raises(MissingColumnError):
                reader.cells(4)

            names = [name for name in reader.cells(0)]

            assert names == ["John", "Mary", "Julia"]

    def test_path(self):
        reader = casanova.reader("./test/resources/people.csv")

        assert list(reader.cells("name")) == ["John", "Mary", "Julia"]

        reader.close()

    def test_context(self):
        with casanova.reader("./test/resources/people.csv") as reader:
            assert list(reader.cells("name")) == ["John", "Mary", "Julia"]

    def test_invalid_identifier_headers(self):
        with casanova.reader("./test/resources/invalid_headers.csv") as reader:
            assert list(reader.cells("Person's name")) == ["John", "Mary", "Julia"]

    def test_static_count(self):
        count = casanova.count(StringIO())

        assert count == 0

        count = casanova.count("./test/resources/people.csv")

        assert count == 3

        count = casanova.count("./test/resources/people.csv", max_rows=10)

        assert count == 3

        count = casanova.count("./test/resources/people.csv", max_rows=1)

        assert count is None

        count = casanova.count("./test/resources/people.csv.gz")

        assert count == 3

    def test_gzip(self):
        with gzip.open("./test/resources/people.csv.gz", "rt") as f:
            reader = casanova.reader(f)

            names = [name for name in reader.cells("name")]

            assert names == ["John", "Mary", "Julia"]

        with casanova.reader("./test/resources/people.csv.gz") as reader:
            names = [name for name in reader.cells("name")]

            assert names == ["John", "Mary", "Julia"]

    def test_bom(self):
        with open("./test/resources/bom.csv", encoding="utf-8") as f:
            reader = casanova.reader(f)

            assert reader.fieldnames == ["name", "color"]
            assert "name" in reader.headers

    def test_wrap(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            for row in reader:
                wrapped = reader.wrap(row)

                assert isinstance(wrapped, RowWrapper)
                assert wrapped["name"] == row[0]
                assert wrapped.surname == row[1]

    def test_prebuffer(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f, prebuffer_bytes=1024)

            assert list(reader.cells("surname")) == ["Matthews", "Sue", "Stone"]
            assert reader.total == 3

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f, prebuffer_bytes=2)

            assert list(reader.cells("surname")) == ["Matthews", "Sue", "Stone"]
            assert reader.total is None

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f, prebuffer_bytes=2)

            for surname in reader.cells("surname"):
                assert surname == "Matthews"
                break

            assert list(reader.cells("surname")) == ["Sue", "Stone"]

    def test_iterable_input(self):
        def generator():
            yield ["name", "surname"]
            yield ["Victor", "Carouso"]
            yield ["Emily", "Harknett"]

        reader = casanova.reader(generator())

        assert list(reader.cells("name")) == ["Victor", "Emily"]

    def test_multiplexing(self):
        with open("./test/resources/multiplex.csv") as f:
            reader = casanova.reader(f, multiplex=Multiplexer("colors", "|"))

            rows = list(reader)

            assert rows == [
                ["John", "blue"],
                ["John", "yellow"],
                ["John", "orange"],
                ["Mary", "purple"],
                ["Mary", "blue"],
                ["Eustache", ""],
                ["Lizbeth", "cyan"],
            ]

        with open("./test/resources/multiplex.csv") as f:
            reader = casanova.reader(f, multiplex=Multiplexer("colors", "|", "color?"))

            cells = list(reader.cells("color?"))

            assert cells == ["blue", "yellow", "orange", "purple", "blue", "", "cyan"]

        with open("./test/resources/multiplex.csv") as f:
            reader = casanova.reader(
                f, multiplex=Multiplexer("colors", "|"), prebuffer_bytes=1024
            )

            assert reader.total == 7

    def test_global_defaults(self):
        with pytest.raises(TypeError):
            set_defaults(prebuffer_bytes=[])

        set_defaults(prebuffer_bytes=1024)

        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            assert list(reader.cells("surname")) == ["Matthews", "Sue", "Stone"]
            assert reader.total == 3

        set_defaults(prebuffer_bytes=None)

        with pytest.raises(TypeError):
            set_defaults(strip_null_bytes_on_read=1324)

        set_defaults(strip_null_bytes_on_read=True)

        with open("./test/resources/with_null_bytes.csv") as f:
            reader = casanova.reader(f)

            rows = list(reader)

            assert rows == [["John", "Zero"], ["Mary", "La Croix"]]

        set_defaults(strip_null_bytes_on_read=False)

    def test_strip_null_bytes_on_read(self):
        with open("./test/resources/with_null_bytes.csv") as f:
            reader = casanova.reader(f, strip_null_bytes_on_read=True)

            rows = list(reader)

            assert rows == [["John", "Zero"], ["Mary", "La Croix"]]

        # It should also work with arbitrary iterables
        data = [["name"], ["Joh\x00n"], ["Mary"]]

        reader = casanova.reader(data, strip_null_bytes_on_read=True)
        rows = list(reader)

        assert rows == [["John"], ["Mary"]]

        # Null byte issues are solved in csv readers from py3.11
        if not LT_PY311:
            return

        with open("./test/resources/with_null_bytes.csv") as f:
            with pytest.raises(LtPy311ByteReadError):
                reader = casanova.reader(f, strip_null_bytes_on_read=False)
                rows = list(reader)

        with open("./test/resources/with_null_bytes.csv") as f:
            with pytest.raises(LtPy311ByteReadError):
                reader = casanova.reader(f)
                rows = list(reader)

    def test_iterable_iterator(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            assert next(reader) == ["John", "Matthews"]
            assert next(reader) == ["Mary", "Sue"]
            assert next(reader) == ["Julia", "Stone"]

            with pytest.raises(StopIteration):
                next(reader)

    def test_no_double_iteration(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            data = list(reader)

            assert len(data) == 3

            for _ in reader:
                assert False

    def test_multiplexing_no_headers(self):
        data = CsvIO([["John", "blue|gray"], ["Paris", "yellow"]])

        with pytest.raises(TypeError, match="multiplexer"):
            reader = casanova.reader(
                StringIO(), no_headers=True, multiplex=Multiplexer(1, new_column="name")
            )

        reader = casanova.reader(data, no_headers=True, multiplex=Multiplexer(1))

        rows = list(reader)

        assert rows == [["John", "blue"], ["John", "gray"], ["Paris", "yellow"]]

    def test_infer_delimiter(self):
        with open("./test/resources/people.tsv") as f:
            people = list(casanova.reader(f))

            assert people == [["Harry", "Golding"], ["James", "Henry"]]

    def test_peek(self):
        with open("./test/resources/people.csv") as f:
            reader = casanova.reader(f)

            assert reader.peek() == ["John", "Matthews"]
            assert reader.peek() == ["John", "Matthews"]

            next(reader)

            assert reader.peek() == ["Mary", "Sue"]

            next(reader)

            assert reader.peek() == ["Julia", "Stone"]

            next(reader)

            # NOTE: yes I am a bit paranoid
            assert reader.peek() is None
            assert reader.peek() is None

            with pytest.raises(StopIteration):
                next(reader)

            assert reader.peek() is None
            assert reader.peek() is None
