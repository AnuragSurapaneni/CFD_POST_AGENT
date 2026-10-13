"""Shared reader interface consumed by statistics and visualization modules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .reader import Snapshot, read_snapshot, referenced_files, snapshots


@dataclass
class Partition:
    index: int
    dataset: object


class KernelData:
    """Read one physical snapshot at a time and expose its local partitions."""

    def __init__(self, input_path: str, time_series: list[dict] | None = None, rank: int = 0, size: int = 1):
        self.snapshots = snapshots(input_path, time_series)
        self.rank = rank
        self.size = size

    def read(self, snapshot: Snapshot) -> Iterator[Partition]:
        datasets = read_snapshot(snapshot.path, rank=self.rank, size=self.size)
        for index, dataset in enumerate(datasets):
            yield Partition(index, dataset)

    def closest_snapshot(self, physical_time: float) -> Snapshot:
        timed = [item for item in self.snapshots if item.time is not None]
        if not timed:
            raise ValueError("This input contains no physical timestamp metadata.")
        matches = [item for item in timed if item.time == float(physical_time)]
        if not matches:
            raise ValueError(f"Timestamp {physical_time} is unavailable. Available: {[item.time for item in timed]}")
        return matches[0]

    def input_bytes(self) -> int:
        total = 0
        for snapshot in self.snapshots:
            unique = set(referenced_files(snapshot.path))
            total += sum(path.stat().st_size for path in unique if path.is_file())
        return total
