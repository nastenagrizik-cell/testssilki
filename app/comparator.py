from __future__ import annotations

from datetime import UTC, datetime

from .models import (
    ComparisonReport,
    Issue,
    ObservedSurvey,
    QuestionMatch,
    QuestionSpec,
    QuestionType,
    SurveySpec,
)
from .normalization import normalize_text, text_similarity


TYPE_COMPATIBILITY = {
    (QuestionType.SINGLE, QuestionType.SCALE),
    (QuestionType.SCALE, QuestionType.SINGLE),
    (QuestionType.SINGLE, QuestionType.MATRIX_SINGLE),
    (QuestionType.MATRIX_SINGLE, QuestionType.SINGLE),
}


def _types_match(expected: QuestionType, observed: QuestionType) -> bool:
    if QuestionType.UNKNOWN in {expected, observed}:
        return True
    return expected == observed or (expected, observed) in TYPE_COMPATIBILITY


def _match_questions(spec: SurveySpec, observed: ObservedSurvey) -> tuple[list[QuestionMatch], set[int], set[int]]:
    candidates: list[tuple[float, int, int, float]] = []
    expected_count = max(1, len(spec.questions) - 1)
    observed_count = max(1, len(observed.questions) - 1)
    for expected_index, expected in enumerate(spec.questions):
        for observed_index, actual in enumerate(observed.questions):
            semantic = text_similarity(expected.text, actual.text)
            order_distance = abs(expected_index / expected_count - observed_index / observed_count)
            adjusted = semantic - min(0.12, 0.12 * order_distance)
            candidates.append((adjusted, expected_index, observed_index, semantic))

    used_expected: set[int] = set()
    used_observed: set[int] = set()
    matches: list[QuestionMatch] = []
    for adjusted, expected_index, observed_index, semantic in sorted(candidates, reverse=True):
        if adjusted < 0.32 or expected_index in used_expected or observed_index in used_observed:
            continue
        expected = spec.questions[expected_index]
        actual = observed.questions[observed_index]
        used_expected.add(expected_index)
        used_observed.add(observed_index)
        matches.append(
            QuestionMatch(
                expected_id=expected.id,
                observed_id=actual.platform_id,
                score=semantic,
                expected_position=expected_index,
                observed_position=observed_index,
            )
        )
    return sorted(matches, key=lambda item: item.expected_position), used_expected, used_observed


def _compare_options(expected: QuestionSpec, actual, issues: list[Issue]) -> None:
    if not expected.options:
        return
    if not actual.options:
        issues.append(
            Issue(
                code="answer_options_missing",
                severity="major",
                title="В ссылке не найдены варианты ответа",
                expected=f"Вариантов в Word: {len(expected.options)}",
                actual="Варианты ответа отсутствуют или не прочитаны",
                question_id=expected.id,
            )
        )
        return
    unmatched_actual = set(range(len(actual.options)))
    for expected_option in expected.options:
        ranked = sorted(
            (
                (text_similarity(expected_option.text, option.text), index, option)
                for index, option in enumerate(actual.options)
                if index in unmatched_actual
            ),
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.55:
            issues.append(
                Issue(
                    code="missing_option",
                    severity="major",
                    title=f"Не найден вариант ответа {expected_option.code}",
                    expected=expected_option.text,
                    question_id=expected.id,
                )
            )
            continue
        score, index, actual_option = ranked[0]
        unmatched_actual.remove(index)
        if score < 0.86:
            issues.append(
                Issue(
                    code="option_text_mismatch",
                    severity="minor",
                    title=f"Отличается формулировка варианта {expected_option.code}",
                    expected=expected_option.text,
                    actual=actual_option.text,
                    question_id=expected.id,
                    evidence={"similarity": score},
                )
            )
        if expected_option.code != actual_option.code:
            issues.append(
                Issue(
                    code="option_code_mismatch",
                    severity="major",
                    title="Код варианта ответа не совпадает",
                    expected=expected_option.code,
                    actual=actual_option.code,
                    question_id=expected.id,
                    evidence={"option": expected_option.text},
                )
            )
        if expected_option.exclusive and not actual_option.exclusive:
            issues.append(
                Issue(
                    code="exclusive_option_missing",
                    severity="major",
                    title="Вариант должен быть исключающим",
                    expected=expected_option.text,
                    actual="На платформе нет признака исключающего варианта",
                    question_id=expected.id,
                )
            )
    for index in sorted(unmatched_actual):
        option = actual.options[index]
        issues.append(
            Issue(
                code="extra_option",
                severity="major",
                title="В ссылке найден лишний вариант ответа",
                actual=f"{option.code}: {option.text}",
                question_id=expected.id,
            )
        )


def _compare_matrix_rows(expected: QuestionSpec, actual, issues: list[Issue]) -> None:
    if not expected.matrix_rows:
        return
    if not actual.matrix_rows:
        issues.append(
            Issue(
                code="matrix_rows_unreadable",
                severity="warning",
                title="Не удалось прочитать строки матрицы на платформе",
                expected=f"Строк в Word: {len(expected.matrix_rows)}",
                question_id=expected.id,
            )
        )
        return
    unmatched_actual = set(range(len(actual.matrix_rows)))
    for expected_row in expected.matrix_rows:
        ranked = sorted(
            (
                (text_similarity(expected_row.text, row.text), index, row)
                for index, row in enumerate(actual.matrix_rows)
                if index in unmatched_actual
            ),
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.55:
            issues.append(
                Issue(
                    code="missing_matrix_row",
                    severity="major",
                    title="В матрице не найдена строка из Word",
                    expected=expected_row.text,
                    question_id=expected.id,
                )
            )
            continue
        score, index, actual_row = ranked[0]
        unmatched_actual.remove(index)
        if score < 0.86:
            issues.append(
                Issue(
                    code="matrix_row_text_mismatch",
                    severity="minor",
                    title="Формулировка строки матрицы отличается",
                    expected=expected_row.text,
                    actual=actual_row.text,
                    question_id=expected.id,
                    evidence={"similarity": score},
                )
            )
    for index in sorted(unmatched_actual):
        issues.append(
            Issue(
                code="extra_matrix_row",
                severity="major",
                title="В ссылке найдена лишняя строка матрицы",
                actual=actual.matrix_rows[index].text,
                question_id=expected.id,
            )
        )


def _unique_orders(samples: list[list[str]]) -> list[tuple[str, ...]]:
    return list(dict.fromkeys(tuple(value for value in sample if value) for sample in samples if sample))


def _compare_rotation(expected: QuestionSpec, actual, issues: list[Issue]) -> None:
    rotation = expected.rotation
    option_orders = _unique_orders(actual.option_order_samples)
    row_orders = _unique_orders(actual.row_order_samples)

    if rotation and rotation.enabled:
        samples = row_orders if rotation.axis == "rows" else option_orders
        if rotation.axis in {"options", "rows", "columns"} and len(samples) == 1 and len(samples[0]) >= 3:
            issues.append(
                Issue(
                    code="rotation_not_observed",
                    severity="major",
                    title="Ротация не обнаружена в независимых запусках",
                    expected=f"Ротация: {rotation.axis}",
                    actual="Порядок не изменился",
                    question_id=expected.id,
                    evidence={"samples": [list(item) for item in samples]},
                )
            )
        if rotation.fixed_codes and option_orders:
            for code in rotation.fixed_codes:
                positions = [order.index(code) for order in option_orders if code in order]
                if len(set(positions)) > 1:
                    issues.append(
                        Issue(
                            code="fixed_option_moved",
                            severity="major",
                            title="Закреплённый вариант меняет позицию",
                            expected=f"Код {code} должен быть закреплён",
                            actual=f"Позиции в запусках: {positions}",
                            question_id=expected.id,
                        )
                    )
    elif len(option_orders) > 1 or len(row_orders) > 1:
        issues.append(
            Issue(
                code="unexpected_rotation",
                severity="major",
                title="Обнаружена ротация, которой нет в Word",
                expected="Стабильный порядок",
                actual="Порядок менялся между независимыми запусками",
                question_id=expected.id,
            )
        )


def compare_surveys(spec: SurveySpec, observed: ObservedSurvey) -> ComparisonReport:
    matches, used_expected, used_observed = _match_questions(spec, observed)
    issues: list[Issue] = []
    by_expected = {match.expected_id: match for match in matches}
    observed_by_id = {question.platform_id: question for question in observed.questions}

    for index, question in enumerate(spec.questions):
        if index not in used_expected:
            issues.append(
                Issue(
                    code="missing_question",
                    severity="critical",
                    title="Вопрос из Word не найден в ссылке",
                    expected=question.text,
                    question_id=question.id,
                )
            )

    for index, question in enumerate(observed.questions):
        if index not in used_observed and question.type != QuestionType.INFO and question.options:
            issues.append(
                Issue(
                    code="extra_question",
                    severity="major",
                    title="В ссылке найден лишний вопрос",
                    actual=question.text,
                    evidence={"platform_id": question.platform_id},
                )
            )

    for expected in spec.questions:
        match = by_expected.get(expected.id)
        if not match:
            continue
        actual = observed_by_id[match.observed_id]
        if match.score < 0.86:
            issues.append(
                Issue(
                    code="question_text_mismatch",
                    severity="major" if match.score < 0.65 else "minor",
                    title="Формулировка вопроса отличается",
                    expected=expected.text,
                    actual=actual.text,
                    question_id=expected.id,
                    evidence={"similarity": match.score},
                )
            )
        if not _types_match(expected.type, actual.type):
            issues.append(
                Issue(
                    code="question_type_mismatch",
                    severity="major",
                    title="Тип вопроса не совпадает",
                    expected=expected.type.value,
                    actual=actual.type.value,
                    question_id=expected.id,
                )
            )
        _compare_options(expected, actual, issues)
        _compare_matrix_rows(expected, actual, issues)
        _compare_rotation(expected, actual, issues)

    observed_positions = [match.observed_position for match in matches]
    if observed_positions != sorted(observed_positions):
        issues.append(
            Issue(
                code="question_order_mismatch",
                severity="major",
                title="Последовательность вопросов отличается от Word",
                expected="Порядок вопросов из Word",
                actual="Порядок вопросов в тестовой ссылке",
            )
        )

    return ComparisonReport(
        created_at=datetime.now(UTC).isoformat(),
        document_title=spec.title,
        platform=observed.platform,
        source_url=observed.source_url,
        expected_question_count=len(spec.questions),
        observed_question_count=len(observed.questions),
        matches=matches,
        issues=issues,
        parser_warnings=spec.warnings,
        platform_warnings=observed.warnings,
    )
