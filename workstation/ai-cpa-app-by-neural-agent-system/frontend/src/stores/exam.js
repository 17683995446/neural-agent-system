import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { examApi } from '../api/exam'

export const useExamStore = defineStore('exam', () => {
  const papers = ref([])
  const currentPaper = ref(null)
  const currentResult = ref(null)
  const answers = ref({})
  const markedQuestions = ref(new Set())
  const loading = ref(false)
  const submitting = ref(false)
  const timeLeft = ref(0)
  const totalTime = ref(0)
  let timerInterval = null

  const currentQuestionIndex = ref(0)
  const currentQuestion = computed(() => {
    if (!currentPaper.value || !currentPaper.value.questions) return null
    return currentPaper.value.questions[currentQuestionIndex.value]
  })
  const totalQuestions = computed(() => currentPaper.value?.questions?.length || 0)
  const answeredCount = computed(() => Object.keys(answers.value).length)

  const fetchPapers = async () => {
    loading.value = true
    try {
      const res = await examApi.getPapers()
      papers.value = res.data
    } finally {
      loading.value = false
    }
  }

  const startExam = async (id) => {
    loading.value = true
    try {
      const res = await examApi.getPaper(id)
      currentPaper.value = res.data
      answers.value = {}
      markedQuestions.value = new Set()
      currentQuestionIndex.value = 0
      totalTime.value = (res.data.duration || 150) * 60
      timeLeft.value = totalTime.value
      startTimer()
    } finally {
      loading.value = false
    }
  }

  const startTimer = () => {
    stopTimer()
    timerInterval = setInterval(() => {
      if (timeLeft.value > 0) {
        timeLeft.value--
      } else {
        stopTimer()
      }
    }, 1000)
  }

  const stopTimer = () => {
    if (timerInterval) {
      clearInterval(timerInterval)
      timerInterval = null
    }
  }

  const setAnswer = (questionId, answer) => {
    answers.value = { ...answers.value, [questionId]: answer }
  }

  const toggleMark = (index) => {
    const newSet = new Set(markedQuestions.value)
    if (newSet.has(index)) newSet.delete(index)
    else newSet.add(index)
    markedQuestions.value = newSet
  }

  const submit = async () => {
    submitting.value = true
    stopTimer()
    try {
      const res = await examApi.submitPaper(currentPaper.value.id, { answers: answers.value, time_used: totalTime.value - timeLeft.value })
      currentResult.value = res.data
      return res.data
    } finally {
      submitting.value = false
    }
  }

  const fetchResult = async (id) => {
    loading.value = true
    try {
      const res = await examApi.getResult(id)
      currentResult.value = res.data
    } finally {
      loading.value = false
    }
  }

  const reset = () => {
    stopTimer()
    currentPaper.value = null
    currentResult.value = null
    answers.value = {}
    markedQuestions.value = new Set()
    currentQuestionIndex.value = 0
    timeLeft.value = 0
    totalTime.value = 0
  }

  return { papers, currentPaper, currentResult, answers, markedQuestions, loading, submitting, timeLeft, totalTime, currentQuestionIndex, currentQuestion, totalQuestions, answeredCount, fetchPapers, startExam, startTimer, stopTimer, setAnswer, toggleMark, submit, fetchResult, reset }
})
