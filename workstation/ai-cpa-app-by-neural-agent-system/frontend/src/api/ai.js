import api from './index'

export const aiApi = {
  diagnosis: (data) => api.post('/ai/diagnosis', data),
  diagnosisSubmit: (data) => api.post('/ai/diagnosis/submit', data),
  recommend: (params) => api.get('/ai/recommend', { params }),
  grade: (data) => api.post('/ai/grade', data),
  explain: (data) => api.post('/ai/explain', data),
  qa: (data) => api.post('/ai/qa', data),
  wrongAnalysis: (data) => api.post('/ai/wrong-analysis', data),
  studyPlan: (params) => api.get('/ai/study-plan', { params })
}
