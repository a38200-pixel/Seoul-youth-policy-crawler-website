import { useCallback, useEffect, useRef, useState } from 'react'
import { api, isAbort } from './client'
import type { Program, ProgramList, TabCounts } from './types'
import type { ProgramQuery } from './client'

export type AsyncState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'ok'; data: T }

/**
 * load 를 실행하고 상태를 돌려준다. key 가 바뀌면 진행 중인 요청을 AbortController 로 취소하고 새로 요청한다
 * (취소된 요청의 응답은 상태에 반영하지 않는다). load 가 null 이면 요청하지 않는다(idle).
 */
export function useRequest<T>(
  load: ((signal: AbortSignal) => Promise<T>) | null,
  key: string,
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: load ? 'loading' : 'idle' })
  const enabled = load !== null

  useEffect(() => {
    // key 가 바뀔 때만 다시 실행된다. 그때의 load(같은 key 의 요청 내용)를 그대로 쓴다.
    if (!load) {
      setState({ status: 'idle' })
      return
    }
    const controller = new AbortController()
    setState({ status: 'loading' })
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: 'ok', data })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        setState({ status: 'error', error })
      })
    return () => controller.abort()
  }, [key, enabled])

  return state
}

export type PagedOptions = {
  enabled: boolean
  query: Omit<ProgramQuery, 'limit' | 'offset'>
  startOffset: number
  pageSize: number
  /** 이 offset 이상은 요청하지 않는다(미정 항목처럼 목록 끝쪽을 따로 보여 줄 때). 없으면 total. */
  endOffset?: number
}

type PagedState = {
  items: Program[]
  total: number
  counts: TabCounts | null
  status: 'idle' | 'loading' | 'ok' | 'error'
  error: unknown
  moreLoading: boolean
  moreError: unknown
  nextOffset: number
}

const initialPaged: PagedState = {
  items: [],
  total: 0,
  counts: null,
  status: 'idle',
  error: null,
  moreLoading: false,
  moreError: null,
  nextOffset: 0,
}

/**
 * /api/programs 를 offset 으로 이어 붙이는 목록. 쿼리·시작 위치가 바뀌면 진행 중인 요청(첫 페이지·더 보기 모두)을 취소하고 처음부터 다시 받는다.
 */
export function usePagedPrograms(options: PagedOptions) {
  const { enabled, query, startOffset, pageSize, endOffset } = options
  const key = JSON.stringify([enabled, query, startOffset, pageSize, endOffset ?? null])
  const [state, setState] = useState<PagedState>(initialPaged)
  const stateRef = useRef(state)
  stateRef.current = state
  const controllerRef = useRef<AbortController | null>(null)
  const optionsRef = useRef(options)
  optionsRef.current = options

  useEffect(() => {
    controllerRef.current?.abort()
    if (!enabled) {
      setState(initialPaged)
      return
    }
    const bound = endOffset ?? Infinity
    if (bound <= startOffset) {
      setState({ ...initialPaged, status: 'ok', nextOffset: startOffset })
      return
    }
    const controller = new AbortController()
    controllerRef.current = controller
    setState({ ...initialPaged, status: 'loading', nextOffset: startOffset })
    const limit = Math.min(pageSize, bound - startOffset)
    api
      .programs({ ...query, limit, offset: startOffset }, controller.signal)
      .then((r: ProgramList) => {
        if (controller.signal.aborted) return
        setState({
          items: r.items,
          total: r.total,
          counts: r.counts,
          status: 'ok',
          error: null,
          moreLoading: false,
          moreError: null,
          nextOffset: startOffset + r.items.length,
        })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        setState({ ...initialPaged, status: 'error', error, nextOffset: startOffset })
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const bound = endOffset ?? state.total
  const hasMore = state.status === 'ok' && state.nextOffset < bound

  const loadMore = useCallback(() => {
    const controller = controllerRef.current
    const current = stateRef.current
    const o = optionsRef.current
    if (!controller || controller.signal.aborted || current.status !== 'ok' || current.moreLoading) return
    const limitBound = o.endOffset ?? current.total
    const limit = Math.min(o.pageSize, limitBound - current.nextOffset)
    if (limit <= 0) return
    setState((s) => ({ ...s, moreLoading: true, moreError: null }))
    api
      .programs({ ...o.query, limit, offset: current.nextOffset }, controller.signal)
      .then((r) => {
        if (controller.signal.aborted) return
        setState((s) => ({
          ...s,
          items: [...s.items, ...r.items],
          total: r.total,
          counts: r.counts,
          moreLoading: false,
          nextOffset: s.nextOffset + r.items.length,
        }))
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        setState((s) => ({ ...s, moreLoading: false, moreError: error }))
      })
  }, [])

  return { ...state, hasMore, loadMore }
}
