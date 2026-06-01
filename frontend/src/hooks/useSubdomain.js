import { useMemo } from 'react'
import { getSubdomain } from '../utils/subdomainHelper'

export function useSubdomain() {
  return useMemo(() => getSubdomain(), [])
}
