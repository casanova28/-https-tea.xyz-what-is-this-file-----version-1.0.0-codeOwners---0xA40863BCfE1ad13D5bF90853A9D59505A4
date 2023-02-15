# =============================================================================
# Casanova Writer
# =============================================================================
#
# A CSV writer that is only really useful if you intend to resume its operation
# somehow
#
import csv

from casanova.defaults import DEFAULTS
from casanova.resuming import Resumer, LastCellResumer
from casanova.reader import Headers
from casanova.utils import py310_wrap_csv_writerow, strip_null_bytes_from_row


class Writer(object):
    __supported_resumers__ = (LastCellResumer,)

    def __init__(self, output_file, fieldnames, strip_null_bytes_on_write=None):
        if strip_null_bytes_on_write is None:
            strip_null_bytes_on_write = DEFAULTS["strip_null_bytes_on_write"]

        if not isinstance(strip_null_bytes_on_write, bool):
            raise TypeError('expecting a boolean as "strip_null_bytes_on_write" kwarg')

        self.strip_null_bytes_on_write = strip_null_bytes_on_write

        self.fieldnames = fieldnames
        self.headers = Headers(fieldnames)

        can_resume = False

        if isinstance(output_file, Resumer):
            resumer = output_file

            if not isinstance(output_file, self.__class__.__supported_resumers__):
                raise TypeError(
                    "%s: does not support %s!"
                    % (self.__class__.__name__, output_file.__class__.__name__)
                )

            can_resume = resumer.can_resume()

            if can_resume:
                resumer.get_insights_from_output(self)

            output_file = resumer.open_output_file()

        self.writer = csv.writer(output_file)
        self._writerow = py310_wrap_csv_writerow(self.writer)

        if not can_resume:
            self.writeheader()

    def writeheader(self):
        row = self.fieldnames

        if self.strip_null_bytes_on_write:
            row = strip_null_bytes_from_row(row)

        self._writerow(row)

    def writerow(self, row):
        self._writerow(
            strip_null_bytes_from_row(row) if self.strip_null_bytes_on_write else row
        )
