export const clusterPalette = ['#2563eb','#0f9f8f','#ee8f35','#8a63d2','#d4547e','#4a7191','#6aa52e','#bd784a']
export const clusterColor = (id: number | null | undefined) => id === null || id === undefined ? '#8ea2b9' : clusterPalette[id % clusterPalette.length]
