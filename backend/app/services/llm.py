"""DeepSeek 调用和学习任务；不记录密钥、原始资料或模型请求。"""
import json
import re
import time
from pathlib import Path

import requests
from flask import current_app

from ..errors import ApiError

PROMPTS = Path(__file__).resolve().parent.parent / 'prompts'


def _prompt(name, values):
    text = (PROMPTS / f'{name}.txt').read_text(encoding='utf-8')
    # 替换模板时不解释用户资料中的大括号。
    return re.sub(r'\{\{(\w+)\}\}', lambda m: str(values.get(m.group(1), '')), text)


def parse_json(content):
    content = content.strip()
    match = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\s*```', content, re.I | re.S)
    if match:
        content = match.group(1).strip()
    try:
        data = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ApiError('LLM_INVALID_RESPONSE', '模型返回的 JSON 格式无效', 502) from exc
    if not isinstance(data, dict):
        raise ApiError('LLM_INVALID_RESPONSE', '模型返回的 JSON 必须是对象', 502)
    return data


def complete(system, user, history=(), json_mode=False):
    config = current_app.config
    if not all(config.get(key) for key in ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL')):
        raise ApiError('LLM_NOT_CONFIGURED', '请先配置模型地址、API Key 和模型名称', 503)
    payload = {'model': config['LLM_MODEL'], 'messages': [{'role': 'system', 'content': system}, *history, {'role': 'user', 'content': user}]}
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    headers = {'Authorization': 'Bearer ' + config['LLM_API_KEY'], 'Content-Type': 'application/json'}
    for attempt in range(4):  # 首次请求 + 最多三次重试
        try:
            response = requests.post(config['LLM_BASE_URL'].rstrip('/') + '/chat/completions', headers=headers, json=payload, timeout=config['LLM_TIMEOUT'])
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise ApiError('LLM_UNAVAILABLE', '模型服务暂时不可用，请稍后重试', 502)
            if not response.ok:
                raise ApiError('LLM_REQUEST_FAILED', f'模型请求失败（HTTP {response.status_code}）', 502)
            try:
                choice = response.json()['choices'][0]
                content = choice['message']['content']
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise ApiError('LLM_INVALID_RESPONSE', '模型响应格式无效', 502) from exc
            if choice.get('finish_reason') != 'stop' or not isinstance(content, str) or not content.strip():
                raise ApiError('LLM_INVALID_RESPONSE', '模型回答为空或不完整', 502)
            return parse_json(content) if json_mode else content
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == 3:
                raise ApiError('LLM_UNAVAILABLE', '模型连接失败，请稍后重试', 502) from exc
            time.sleep(2 ** attempt)
    raise ApiError('LLM_UNAVAILABLE', '模型服务暂时不可用', 502)


def _material_text(chunks):
    text = json.dumps(chunks, ensure_ascii=False)
    if len(text) > current_app.config['LLM_MAX_CONTEXT_CHARS']:
        raise ApiError('MATERIAL_TOO_LONG', '所选资料超出当前模型上下文配置，请选择较短的资料', 400)
    return text


def chat(question, chunks, history):
    data = _material_text(chunks)
    system = _prompt('chat', {'material_chunks': data, 'user_question': question})
    system += '\n请用 JSON 返回 {"answer":"回答内容", "source_chunk_ids":["实际引用的片段ID"]}。没有引用时数组为空。'
    result = complete(system, question, history, json_mode=True)
    ids = result.get('source_chunk_ids')
    allowed = {c['id'] for c in chunks}
    if not isinstance(result.get('answer'), str) or not isinstance(ids, list) or any(not isinstance(i, str) or i not in allowed for i in ids):
        raise ApiError('LLM_INVALID_RESPONSE', '模型回答或引用格式无效', 502)
    return result


def generate_questions(chunks, counts, existing):
    system = _prompt('questions', {'material_chunks': _material_text(chunks), 'question_counts': json.dumps(counts, ensure_ascii=False), 'existing_knowledge_points': json.dumps(existing, ensure_ascii=False)})
    system += '\n请混合简单、中等、较难三种难度；每题增加 difficulty 字段，值为简单、中等或较难。'
    result = complete(system, '请根据资料生成符合要求的 JSON 题目。', json_mode=True)
    questions = result.get('questions')
    allowed = {c['id'] for c in chunks}
    if not isinstance(questions, list):
        raise ApiError('LLM_INVALID_RESPONSE', '模型未返回题目列表', 502)
    seen = {key: 0 for key in counts}
    for q in questions:
        if not isinstance(q, dict) or q.get('type') not in counts or not isinstance(q.get('content'), str) or not q['content'].strip() or not isinstance(q.get('source_chunk_ids'), list) or not q['source_chunk_ids'] or any(not isinstance(source, str) or source not in allowed for source in q['source_chunk_ids']) or not isinstance(q.get('knowledge_points'), list) or not q['knowledge_points'] or not all(isinstance(k, str) and k.strip() for k in q['knowledge_points']):
            raise ApiError('LLM_INVALID_RESPONSE', '生成题目的内容或资料来源无效', 502)
        typ = q['type']; seen[typ] += 1
        if seen[typ] > counts[typ] or q.get('difficulty') not in ('简单','中等','较难'):
            raise ApiError('LLM_INVALID_RESPONSE', '生成题目的数量或难度无效', 502)
        if typ == 'single_choice':
            options = q.get('options')
            if not isinstance(options,list) or len(options)!=4 or not all(isinstance(o,dict) and isinstance(o.get('content'),str) and o['content'].strip() for o in options) or {o.get('key') for o in options} != {'A','B','C','D'} or q.get('correct_answer') not in ('A','B','C','D'):
                raise ApiError('LLM_INVALID_RESPONSE', '生成的选择题无效', 502)
        elif typ == 'true_false' and type(q.get('correct_answer')) is not bool:
            raise ApiError('LLM_INVALID_RESPONSE', '生成的判断题无效', 502)
        elif typ == 'short_answer' and (not isinstance(q.get('correct_answer'),str) or not q['correct_answer'].strip() or not isinstance(q.get('grading_points'),list) or not q['grading_points']):
            raise ApiError('LLM_INVALID_RESPONSE', '生成的简答题评分依据无效', 502)
    return result


def grade(question, answer, chunks):
    if question.type != 'short_answer':
        score = int(type(answer) is type(question.correct_answer) and answer == question.correct_answer)
        return {'score': score, 'feedback': '回答正确。' if score else '回答错误。', 'needs_review': False, 'review_reason': None}
    if answer is None or not str(answer).strip():
        return {'score': 0, 'feedback': '未作答。', 'needs_review': False, 'review_reason': None}
    system = _prompt('grading', {'question': question.content, 'correct_answer': question.correct_answer, 'grading_points': json.dumps(question.grading_points,ensure_ascii=False), 'source_chunks': _material_text(chunks), 'user_answer': answer})
    result = complete(system, '请按要求返回 JSON 评分结果。', json_mode=True)
    score = result.get('score'); review = result.get('needs_review')
    if type(review) is not bool or (review and (score is not None or not result.get('review_reason'))) or (not review and (type(score) not in (int,float) or score not in (0,0.5,1))) or not isinstance(result.get('feedback'),str):
        raise ApiError('LLM_INVALID_RESPONSE', '模型评分格式无效', 502)
    return result


def weekly_report(data):
    return complete('你是学习报告助手。只根据给定记录总结学习内容和薄弱点，提出下周建议；没有数据则明确说明，不编造。用 Markdown 标题和列表输出。', json.dumps(data,ensure_ascii=False))
