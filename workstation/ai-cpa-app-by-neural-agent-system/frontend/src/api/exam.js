import api from './index'

export const examApi = {
  getPapers: () => api.get('/exam/papers'),
  getPaper: (id) => api.get(`/exam/papers/${id}`),
  submitPaper: (id, data) => api.post(`/exam/papers/${id}/submit`, data),
  getResult: (id) => api.get(`/exam/results/${id}`)
}
