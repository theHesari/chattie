def test_test_db_is_isolated(owner_conn, test_db_name):
    assert test_db_name.startswith("chattie_test_")
    assert owner_conn.execute("select current_database()").fetchone()[0] == test_db_name
