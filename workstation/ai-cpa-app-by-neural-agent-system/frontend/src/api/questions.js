import api from './index'

export const questionApi = {
  getQuestions: (params) => api.get('/questions', { params }),
  getQuestion: (id) => api.get(`/questions/${id}`),
  getCount: () => api.get('/questions/count')
}
