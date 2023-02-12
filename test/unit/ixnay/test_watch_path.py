from pathlib import Path

from git_graph_branch.ixnay import watch_path
from git_graph_branch.ixnay.testing import FakeNixer, ManualObserver


def test_watch_file_creation(tmp_path: Path, manual_observer: ManualObserver) -> None:
    nixer = FakeNixer()
    file = tmp_path / "example.txt"
    watch_path(file, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file.touch()
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_file_modification(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    file = tmp_path / "example.txt"
    file.touch()
    watch_path(file, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    with open(file, "w") as s:
        print("some text", file=s)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_file_deletion(tmp_path: Path, manual_observer: ManualObserver) -> None:
    nixer = FakeNixer()
    file = tmp_path / "example.txt"
    file.touch()
    watch_path(file, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file.unlink()
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_file_rename_source(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    file1 = tmp_path / "example.txt"
    file2 = tmp_path / "other.txt"
    file1.touch()
    watch_path(file1, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file1.rename(file2)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_file_rename_destination(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    file1 = tmp_path / "example.txt"
    file2 = tmp_path / "other.txt"
    file1.touch()
    watch_path(file2, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file1.rename(file2)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_creation(tmp_path: Path, manual_observer: ManualObserver) -> None:
    nixer = FakeNixer()
    dir = tmp_path / "example"
    watch_path(dir, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    dir.mkdir()
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_deletion(tmp_path: Path, manual_observer: ManualObserver) -> None:
    nixer = FakeNixer()
    dir = tmp_path / "example"
    dir.mkdir()
    watch_path(dir, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    dir.rmdir()
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_rename_source(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    dir1 = tmp_path / "example"
    dir2 = tmp_path / "other"
    dir1.mkdir()
    watch_path(dir1, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    dir1.rename(dir2)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_rename_destination(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    dir1 = tmp_path / "example"
    dir2 = tmp_path / "other"
    dir1.mkdir()
    watch_path(dir2, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    dir1.rename(dir2)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_file_creation(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    dir = tmp_path / "somedir"
    dir.mkdir()
    file = dir / "example.txt"
    watch_path(dir, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file.touch()
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_file_modification(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    dir = tmp_path / "somedir"
    dir.mkdir()
    file = dir / "example.txt"
    file.touch()
    watch_path(dir, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    with open(file, "w") as s:
        print("some text", file=s)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_file_deletion(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    dir = tmp_path / "somedir"
    dir.mkdir()
    file = dir / "example.txt"
    file.touch()
    watch_path(dir, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file.unlink()
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_file_rename_source(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    dir1 = tmp_path / "somedir"
    dir1.mkdir()
    dir2 = tmp_path / "someotherdir"
    dir2.mkdir()
    file1 = dir1 / "example.txt"
    file2 = dir2 / "example.txt"
    file1.touch()
    watch_path(dir1, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file1.rename(file2)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_dir_file_rename_destination(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    nixer = FakeNixer()
    dir1 = tmp_path / "somedir"
    dir1.mkdir()
    dir2 = tmp_path / "someotherdir"
    dir2.mkdir()
    file1 = dir1 / "example.txt"
    file2 = dir2 / "example.txt"
    file1.touch()
    watch_path(dir2, nixer)
    manual_observer.check_for_changes()
    assert not nixer.is_nixed
    file1.rename(file2)
    manual_observer.check_for_changes()
    assert nixer.is_nixed


def test_watch_multiple_locations(
    tmp_path: Path, manual_observer: ManualObserver
) -> None:
    file1 = tmp_path / "example.txt"
    file2 = tmp_path / "other.txt"
    file3 = tmp_path / "third.txt"
    file1.touch()

    nixer1 = FakeNixer()
    watch_path(file1, nixer1, root_path=tmp_path)
    nixer2 = FakeNixer()
    watch_path(file2, nixer2, root_path=tmp_path)
    nixer3 = FakeNixer()
    watch_path(file3, nixer3, root_path=tmp_path)

    manual_observer.check_for_changes()
    assert not nixer1.is_nixed
    assert not nixer2.is_nixed
    assert not nixer3.is_nixed

    with open(file1, "w") as s:
        print("some text", file=s)

    manual_observer.check_for_changes()
    assert nixer1.is_nixed
    assert not nixer2.is_nixed
    assert not nixer3.is_nixed
    nixer1 = FakeNixer()
    watch_path(file1, nixer1, root_path=tmp_path)

    file2.touch()

    manual_observer.check_for_changes()
    assert not nixer1.is_nixed
    assert nixer2.is_nixed
    assert not nixer3.is_nixed
    nixer2 = FakeNixer()
    watch_path(file2, nixer2, root_path=tmp_path)

    file1.rename(file3)

    manual_observer.check_for_changes()
    assert nixer1.is_nixed
    assert not nixer2.is_nixed
    assert nixer3.is_nixed
