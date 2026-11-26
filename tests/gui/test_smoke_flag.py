from plumbcenter.gui import app as gui_app


def test_smoke_flag_shows_window_and_exits_zero(qapp):
    assert gui_app.main(["plumbcenter", "--smoke-test"]) == 0
