import api from './index'

export const courseApi = {
  getCourses: (params) => api.get('/courses', { params }),
  getCourse: (id) => api.get(`/courses/${id}`),
  addNote: (id, data) => api.post(`/courses/${id}/note`, data)
}
