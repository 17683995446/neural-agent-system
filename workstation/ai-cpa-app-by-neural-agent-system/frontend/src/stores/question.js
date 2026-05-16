import { defineStore } from 'pinia'
import { ref } from 'vue'
import { questionApi } from '../api/questions'

export const useQuestionStore = defineStore('question', () => {
  const questions = ref([])
  const currentQuestion = ref(null)
  const total = ref(0)
  const page = ref(1)
  const size = ref(20)
  const loading = ref(false)
  const currentIndex = ref(0)
  const userAnswer = ref(null)
  const gradeResult = ref(null)
  const explanation = ref(null)

  const fetchQuestions = async (filters = {}) => {
    loading.value = true
    try {
      const params = { page: page.value, size: size.value, ...filters }
      const res = await questionApi.getQuestions(params)
      questions.value = res.data.items || res.data
      total.value = res.data.total || 0
    } finally {
      loading.value = false
    }
  }

  const fetchQuestion = async (id) => {
    loading.value = true
    try {
      const res = await questionApi.getQuestion(id)
      currentQuestion.value = res.data
    } finally {
      loading.value = false
    }
  }

  const setCurrentQuestion = (index) => {
    if (index >= 0 && index < questions.value.length) {
      currentIndex.value = index
      currentQuestion.value = questions.value[index]
      userAnswer.value = null
      gradeResult.value = null
      explanation.value = null
    }
  }

  const next = () => setCurrentQuestion(currentIndex.value + 1)
  const prev = () => setCurrentQuestion(currentIndex.value - 1)

  const reset = () => {
    questions.value = []
    currentQuestion.value = null
    currentIndex.value = 0
    userAnswer.value = null
    gradeResult.value = null
    explanation.value = null
  }

  return { questions, currentQuestion, total, page, size, loading, currentIndex, userAnswer, gradeResult, explanation, fetchQuestions, fetchQuestion, setCurrentQuestion, next, prev, reset }
})
