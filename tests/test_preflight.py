"""Tests for the BirdNET-Go input check (make the diagnostic actionable)."""

import sqlite3

import pytest

from birdhouse.app import check_birdnet_inputs


@pytest.fixture
def inputs(tmp_path):
    db = tmp_path / "birdnet.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE labels (id INTEGER PRIMARY KEY, scientific_name TEXT, model_id INTEGER);
        CREATE TABLE detections (id INTEGER PRIMARY KEY, label_id INTEGER,
                                 detected_at INTEGER, confidence REAL);
    """)
    conn.close()

    taxonomy = tmp_path / "taxonomy.csv"
    taxonomy.write_text(
        "idx,sci_name,com_name,class_name\n"
        "0,Corvus brachyrhynchos,American Crow,aves\n",
        encoding="utf-8",
    )
    return db, taxonomy


class TestCheckBirdnetInputs:
    def test_accepts_the_schema_birdhouse_reads(self, inputs):
        db, taxonomy = inputs
        assert check_birdnet_inputs(db, taxonomy) == ""

    def test_missing_database_names_the_path(self, tmp_path, inputs):
        _, taxonomy = inputs
        problem = check_birdnet_inputs(tmp_path / "nope.db", taxonomy)
        assert "isn't at" in problem and "nope.db" in problem

    def test_missing_table_is_named(self, tmp_path, inputs):
        _, taxonomy = inputs
        db = tmp_path / "no-detections.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE labels (id INTEGER PRIMARY KEY, scientific_name TEXT)")
        conn.close()
        assert "no detections table" in check_birdnet_inputs(db, taxonomy)

    def test_missing_column_is_named(self, tmp_path, inputs):
        _, taxonomy = inputs
        db = tmp_path / "no-confidence.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE labels (id INTEGER PRIMARY KEY, scientific_name TEXT);
            CREATE TABLE detections (id INTEGER PRIMARY KEY, label_id INTEGER, detected_at INTEGER);
        """)
        conn.close()
        problem = check_birdnet_inputs(db, taxonomy)
        assert "detections table is missing confidence" in problem

    def test_missing_taxonomy_names_the_path(self, inputs, tmp_path):
        db, _ = inputs
        problem = check_birdnet_inputs(db, tmp_path / "nope.csv")
        assert "taxonomy.csv isn't at" in problem

    def test_taxonomy_missing_a_column(self, inputs):
        db, taxonomy = inputs
        taxonomy.write_text("idx,sci_name,com_name\n0,Corvus brachyrhynchos,American Crow\n")
        problem = check_birdnet_inputs(db, taxonomy)
        assert "class_name" in problem

    def test_empty_taxonomy_is_unreadable_shape(self, inputs):
        db, taxonomy = inputs
        taxonomy.write_text("")
        problem = check_birdnet_inputs(db, taxonomy)
        assert "sci_name" in problem and "class_name" in problem

    def test_a_directory_in_the_db_path_is_not_a_database(self, tmp_path, inputs):
        _, taxonomy = inputs
        problem = check_birdnet_inputs(tmp_path, taxonomy)
        assert "could not be read" in problem
