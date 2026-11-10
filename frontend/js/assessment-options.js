const JUDGMENT_OPTIONS = { A: '正确', B: '错误' };

export function questionOptions(question) {
  if (question.type === 'true_false') {
    return Object.entries(JUDGMENT_OPTIONS).map(([key, content]) => ({ key, content }));
  }
  let options = question.options;
  if (typeof options === 'string') {
    try { options = JSON.parse(options); }
    catch { throw new Error('题目选项格式无效'); }
  }
  if (options && !Array.isArray(options) && typeof options === 'object') {
    options = Object.entries(options).map(([key, content]) => ({ key, content }));
  }
  if (!Array.isArray(options) || options.length !== 4 ||
      !options.every(item => item && typeof item.key === 'string' && typeof item.content === 'string') ||
      new Set(options.map(item => item.key)).size !== 4 ||
      !['A', 'B', 'C', 'D'].every(key => options.some(item => item.key === key))) {
    throw new Error('题目选项格式无效');
  }
  return options;
}

export function answerValue(type, key) {
  return type === 'true_false' ? key === 'A' : key;
}
