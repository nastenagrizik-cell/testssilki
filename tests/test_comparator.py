import unittest

from app.comparator import compare_surveys
from app.models import (
    AnswerOption,
    ObservedQuestion,
    ObservedSurvey,
    QuestionSpec,
    QuestionType,
    RotationSpec,
    SourceLocation,
    SurveySpec,
)


def expected_question(qid: str, text: str, options: list[AnswerOption]) -> QuestionSpec:
    return QuestionSpec(
        id=qid,
        text=text,
        type=QuestionType.SINGLE,
        options=options,
        source=SourceLocation(block_index=1, kind="paragraph"),
    )


class ComparatorTests(unittest.TestCase):
    def test_identical_surveys_have_no_issues(self):
        options = [AnswerOption(code="1", text="Да"), AnswerOption(code="2", text="Нет")]
        spec = SurveySpec(title="Тест", questions=[expected_question("Q1", "Вы согласны?", options)])
        observed = ObservedSurvey(
            platform="enjoysurvey",
            source_url="https://example.test/survey",
            questions=[
                ObservedQuestion(
                    platform_id="11",
                    text="Вы согласны?",
                    type=QuestionType.SINGLE,
                    options=options,
                )
            ],
        )

        report = compare_surveys(spec, observed)

        self.assertEqual(report.issues, [])

    def test_reports_missing_option_and_extra_question(self):
        spec = SurveySpec(
            title="Тест",
            questions=[
                expected_question(
                    "Q1",
                    "Выберите напиток",
                    [AnswerOption(code="1", text="Чай"), AnswerOption(code="2", text="Кофе")],
                )
            ],
        )
        observed = ObservedSurvey(
            platform="enjoysurvey",
            source_url="https://example.test/survey",
            questions=[
                ObservedQuestion(
                    platform_id="11",
                    text="Выберите напиток",
                    type=QuestionType.SINGLE,
                    options=[AnswerOption(code="1", text="Чай")],
                ),
                ObservedQuestion(
                    platform_id="12",
                    text="Лишний вопрос",
                    type=QuestionType.SINGLE,
                    options=[AnswerOption(code="1", text="Да")],
                ),
            ],
        )

        report = compare_surveys(spec, observed)
        codes = {issue.code for issue in report.issues}

        self.assertIn("missing_option", codes)
        self.assertIn("extra_question", codes)

    def test_reports_missing_and_unexpected_rotation(self):
        options = [
            AnswerOption(code="1", text="Первый"),
            AnswerOption(code="2", text="Второй"),
            AnswerOption(code="3", text="Третий"),
        ]
        rotating = expected_question("Q1", "Вопрос с ротацией", options)
        rotating.rotation = RotationSpec(enabled=True, axis="options")
        stable = expected_question("Q2", "Вопрос без ротации", options)
        spec = SurveySpec(title="Тест", questions=[rotating, stable])
        observed = ObservedSurvey(
            platform="enjoysurvey",
            source_url="https://example.test/survey",
            questions=[
                ObservedQuestion(
                    platform_id="11",
                    text="Вопрос с ротацией",
                    type=QuestionType.SINGLE,
                    options=options,
                    option_order_samples=[["1", "2", "3"], ["1", "2", "3"], ["1", "2", "3"]],
                ),
                ObservedQuestion(
                    platform_id="12",
                    text="Вопрос без ротации",
                    type=QuestionType.SINGLE,
                    options=options,
                    option_order_samples=[["1", "2", "3"], ["2", "1", "3"]],
                ),
            ],
        )

        codes = {issue.code for issue in compare_surveys(spec, observed).issues}

        self.assertIn("rotation_not_observed", codes)
        self.assertIn("unexpected_rotation", codes)

    def test_compares_matrix_rows(self):
        question = expected_question("Q1", "Оцените характеристики", [])
        question.type = QuestionType.MATRIX_SINGLE
        question.matrix_rows = [
            AnswerOption(code="1", text="Вкус"),
            AnswerOption(code="2", text="Внешний вид"),
        ]
        observed = ObservedSurvey(
            platform="enjoysurvey",
            source_url="https://example.test/survey",
            questions=[
                ObservedQuestion(
                    platform_id="11",
                    text="Оцените характеристики",
                    type=QuestionType.MATRIX_SINGLE,
                    matrix_rows=[AnswerOption(code="1", text="Вкус")],
                )
            ],
        )

        codes = {issue.code for issue in compare_surveys(SurveySpec(title="Тест", questions=[question]), observed).issues}

        self.assertIn("missing_matrix_row", codes)

    def test_reports_when_all_answer_options_are_absent(self):
        options = [AnswerOption(code="1", text="Да"), AnswerOption(code="2", text="Нет")]
        spec = SurveySpec(title="Тест", questions=[expected_question("Q1", "Вы согласны?", options)])
        observed = ObservedSurvey(
            platform="enjoysurvey",
            source_url="https://example.test/survey",
            questions=[ObservedQuestion(platform_id="11", text="Вы согласны?", type=QuestionType.SINGLE)],
        )

        codes = {issue.code for issue in compare_surveys(spec, observed).issues}

        self.assertIn("answer_options_missing", codes)


if __name__ == "__main__":
    unittest.main()
