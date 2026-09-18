from app.domain.control import ADVISORY, extract_control_options, extract_safe_control_principles, sanitize_answer


def test_control_options_strip_usage_parameters():
    options = extract_control_options("化学防治：20%三环唑1000倍液。农业防治：轮作。", "d1", "稻瘟病")
    assert [(item["name"], item["type"]) for item in options] == [("三环唑", "ACTIVE_INGREDIENT"), ("农业防治原则", "AGRICULTURAL")]


def test_answer_boundary_removes_dose_and_handles_dose_question():
    answer, changed = sanitize_answer("可使用三环唑。每亩用100克兑水喷雾。", "稻瘟病用什么药")
    assert changed is True
    assert "100克" not in answer
    assert "三环唑" in answer
    assert sanitize_answer("ignored", "具体剂量是多少")[0] == ADVISORY


def test_safe_control_principles_keep_cultural_advice_without_dose() -> None:
    value = extract_safe_control_principles("农业防治：实行轮作，清除病残体。化学防治：20%三环唑1000倍液喷雾。")
    assert "轮作" in value
    assert "病残体" in value
    assert "20%" not in value
    assert "1000倍" not in value
    assert "浸种" not in value
