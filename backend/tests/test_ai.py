import json
import unittest
from unittest.mock import Mock, patch

import requests

from app import create_app
from app.errors import ApiError
from app.extensions import db
from app.models import Material, MaterialChunk
from app.services import llm


class AIIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'LLM_API_KEY': 'test', 'LLM_MODEL': 'test', 'LLM_BASE_URL': 'https://example.test/v1'})
        self.ctx = self.app.app_context(); self.ctx.push(); db.create_all()
        m = Material(id='m1',user_id='dev-user',name='课程.md',file_type='md',file_path='test',status='ready')
        db.session.add(m); db.session.add(MaterialChunk(id='c1',material_id='m1',content='注意力机制可以聚合上下文信息。',chunk_order=0));db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove();db.drop_all();self.ctx.pop()

    @staticmethod
    def response(content):
        response=Mock(ok=True,status_code=200)
        response.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':content}}]}
        return response

    @patch('app.services.llm.time.sleep')
    @patch('app.services.llm.requests.post')
    def test_retry_fenced_json_and_sources(self, post, sleep):
        post.side_effect=[requests.Timeout(),self.response('```json\n{"answer":"聚合上下文","source_chunk_ids":["c1"]}\n```')]
        conversation=self.client.post('/api/v1/conversations',json={'material_ids':['m1']}).get_json()['data']['id']
        response=self.client.post(f'/api/v1/conversations/{conversation}/messages',json={'content':'注意力是什么？'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['data']['assistant_message']['sources'][0]['chunk_id'],'c1')
        self.assertEqual(post.call_count,2);sleep.assert_called_once()
        messages=self.client.get(f'/api/v1/conversations/{conversation}/messages').get_json()['data']['items']
        self.assertEqual(len(messages),2)

    @patch('app.services.llm.time.sleep')
    @patch('app.services.llm.requests.post',side_effect=requests.Timeout())
    def test_retry_limit(self,post,sleep):
        with self.assertRaises(ApiError): llm.complete('system','user')
        self.assertEqual(post.call_count,4)

    @patch('app.services.llm.requests.post')
    def test_questions_grade_and_report(self,post):
        question={'type':'single_choice','content':'什么是注意力？','options':[{'key':k,'content':k} for k in 'ABCD'],'correct_answer':'A','grading_points':None,'knowledge_points':['注意力'],'source_chunk_ids':['c1'],'difficulty':'简单'}
        post.side_effect=[self.response(json.dumps({'questions':[question],'shortfalls':[]},ensure_ascii=False)),self.response('# 学习周报\n- 学习了注意力')]
        create=self.client.post('/api/v1/assessments',json={'material_ids':['m1'],'question_counts':{'single_choice':1,'true_false':0,'short_answer':0}})
        self.assertEqual(create.status_code,200); aid=create.get_json()['data']['id']
        q=self.client.get(f'/api/v1/assessments/{aid}').get_json()['data']['questions'][0]
        self.assertNotIn('correct_answer',q)
        submitted=self.client.post(f'/api/v1/assessments/{aid}/submit',json={'answers':[{'question_id':q['id'],'answer':'A'}]})
        self.assertEqual(submitted.get_json()['data']['status'],'completed')
        result=self.client.get(f'/api/v1/assessments/{aid}/result').get_json()['data']
        self.assertEqual(result['total_score'],1)
        from datetime import date,timedelta
        today=date.today(); monday=today-timedelta(days=today.weekday())
        report=self.client.post('/api/v1/weekly-reports',json={'week_start':monday.isoformat()})
        self.assertEqual(report.status_code,200);self.assertIn('学习周报',report.get_json()['data']['report_data']['content'])

    @patch('app.services.llm.requests.post')
    def test_short_answer_invalid_score(self,post):
        post.return_value=self.response('{"score":0.7,"feedback":"","needs_review":false,"review_reason":null}')
        question=Mock(type='short_answer',content='问题',correct_answer='答案',grading_points=['要点'])
        with self.assertRaises(ApiError): llm.grade(question,'回答',[])


if __name__ == '__main__': unittest.main()
