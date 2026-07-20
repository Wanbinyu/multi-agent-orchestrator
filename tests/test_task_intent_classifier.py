"""Phase 7.1 任务分类与保守策略测试。"""
from __future__ import annotations

import pytest

from src.core.engineering import TaskIntentClassifier


@pytest.mark.parametrize(
    ("text", "kind", "allows_writes"),
    [
        ("现在上下文是不是 32K？", "answer", False),
        ("解释一下这段代码的工作原理", "explain", False),
        ("为什么 CLI 会重复显示，帮我排查原因", "diagnose", False),
        ("检查 G:\\MAO_test 的项目结构", "review", False),
        ("修复登录接口的 500 错误", "change", True),
        ("实现一个前后端登录功能", "build", True),
        ("开发登录功能", "build", True),
        ("写文件", "build", True),
        ("写文件 native.txt，内容为 hello", "build", True),
        ("创建 src/main.py，并提供返回 ok 的 health 函数", "build", True),
        ("先做 Java 重构方案，不要修改文件", "plan", False),
        ("持续监控测试进程，完成后通知", "monitor", False),
    ],
)
def test_classifier_maps_common_requests(text, kind, allows_writes):
    intent = TaskIntentClassifier().classify(text, "auto")

    assert intent.kind == kind
    assert intent.policy.allow_project_writes is allows_writes
    assert intent.write_authorized is (allows_writes is True)


def test_write_action_wins_over_review_wording():
    intent = TaskIntentClassifier().classify("检查登录代码并修复鉴权错误", "auto")

    assert intent.kind == "change"
    assert intent.policy.allow_project_writes is True


@pytest.mark.parametrize(
    "text",
    [
        "我现在接了一个项目，让我做一个矿场智能检测系统，但是时间太紧了，所以我需要你帮我先做一个纯前端的界面，放在G:\\MAO_test，但是我需要把项目结构先简单搭建好，后面方便我直接进行后续工作和开发",
        "我需要你帮我先做一个登录页面",
        "帮我做一套数据看板",
        "把项目结构搭建好",
        "把首页布局做出来",
    ],
)
def test_mid_sentence_build_phrasing_is_recognized(text):
    """句中的"帮我做/把……搭建好"同样构成明确写入授权。"""
    intent = TaskIntentClassifier().classify(text, "auto")

    assert intent.kind == "build"
    assert intent.policy.allow_project_writes is True
    assert intent.write_authorized is True


@pytest.mark.parametrize(
    "text",
    [
        "我现在接了一个智慧矿区的项目，现在给我做一个纯前端的项目，放在G:\\MAO_test",
        "现在给我做一套后台管理界面",
        "在 G:\\MAO_test 中做一个项目",
    ],
)
def test_real_natural_language_project_build_requests_are_high_risk(text):
    intent = TaskIntentClassifier().classify(text, "auto")

    assert intent.kind == "build"
    assert intent.risk_level == "high"
    assert intent.policy.verification_depth == "deep"
    assert intent.policy.requires_plan is True
    assert intent.policy.collaboration_allowed is True
    assert intent.write_authorized is True


def test_create_it_for_me_followup_is_a_writable_build():
    intent = TaskIntentClassifier().classify("帮我创建好", "auto")

    assert intent.kind == "build"
    assert intent.policy.allow_project_writes is True
    assert intent.write_authorized is True


@pytest.mark.parametrize(
    "text",
    [
        "帮我看看怎么做这个页面",
        "帮我做版本对比",
        "把项目搭建的事告诉我",
        "告诉我怎么做一个项目",
        "给我说一下怎么做一个前端项目",
        "如果在 G:\\MAO_test 做一个项目，需要什么技术栈？",
    ],
)
def test_similar_readonly_phrasing_does_not_grant_writes(text):
    """"怎么做/做对比/告诉我"类问法不得误判为写入。"""
    intent = TaskIntentClassifier().classify(text, "auto")

    assert intent.policy.allow_project_writes is False


def test_explaining_how_to_write_a_file_stays_readonly():
    intent = TaskIntentClassifier().classify("解释如何写文件", "auto")

    assert intent.kind == "explain"
    assert intent.policy.allow_project_writes is False


@pytest.mark.parametrize(
    "text",
    [
        "未来有没有调整上下文的计划？",
        "帮我检查一下整体结构有没有需要优化的",
        "这个问题是否可以修复？",
        "怎么修改配置比较合理？",
    ],
)
def test_write_words_inside_questions_do_not_grant_write_access(text):
    intent = TaskIntentClassifier().classify(text, "auto")

    assert intent.kind in {"answer", "review"}
    assert intent.policy.allow_project_writes is False
    assert intent.write_authorized is False


def test_explicit_plan_boundary_wins_over_future_build_wording():
    intent = TaskIntentClassifier().classify(
        "分析项目，我想用 Java 重做，先做重构方案，不修改文件",
        "auto",
    )

    assert intent.kind == "plan"
    assert intent.policy.allow_project_writes is False
    assert intent.policy.requires_plan is True


def test_no_write_diagnostic_remains_diagnose():
    intent = TaskIntentClassifier().classify("只分析这个报错，不要修改代码", "auto")

    assert intent.kind == "diagnose"
    assert intent.write_authorized is False


def test_approve_mode_requires_later_write_approval():
    classifier = TaskIntentClassifier()

    approve = classifier.classify("修复这个问题", "approve")
    readonly = classifier.classify("修复这个问题", "readonly")

    assert approve.policy.allow_project_writes is True
    assert approve.write_authorized is False
    assert readonly.policy.allow_project_writes is True
    assert readonly.write_authorized is False


def test_unclassified_task_uses_session_permission_mode():
    classifier = TaskIntentClassifier()

    auto = classifier.classify("处理一下", "auto")
    approve = classifier.classify("处理一下", "approve")
    readonly = classifier.classify("处理一下", "readonly")

    assert auto.policy.allow_project_writes is False
    assert auto.policy.permission_follows_session is True
    assert auto.write_authorized is True
    assert approve.policy.allow_project_writes is False
    assert approve.policy.permission_follows_session is True
    assert approve.write_authorized is False
    assert readonly.policy.allow_project_writes is False
    assert readonly.policy.permission_follows_session is True
    assert readonly.write_authorized is False


def test_short_continuation_inherits_previous_intent():
    classifier = TaskIntentClassifier()
    previous = classifier.classify("实现一个登录功能", "approve")

    intent = classifier.classify("继续", "auto", previous_intent=previous)

    assert intent.kind == "build"
    assert intent.classification_source == "inherited"
    assert intent.write_authorized is True


def test_classifier_extracts_explicit_windows_scope():
    intent = TaskIntentClassifier().classify(
        "检查 G:\\MAO_test 和 E:/multi-agent-orchestrator 的结构",
        "approve",
    )

    assert intent.scope == ["G:\\MAO_test", "E:/multi-agent-orchestrator"]
