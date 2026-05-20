export const motionTokens = {
    duration: {
        instant: 0,
        faster: 0.1,
        fast: 0.15,
        normal: 0.3,
        slow: 0.5,
        slower: 0.8
    },

    easing: {
        standard: [0.4, 0, 0.2, 1],
        emphasized: [0.2, 0, 0, 1],
        industrial: [0.25, 0.1, 0.25, 1],
        bauhaus: [0.61, 1, 0.88, 1]
    },

    spring: {
        snappy: { stiffness: 400, damping: 30 },
        gentle: { stiffness: 100, damping: 15, mass: 0.5 },
        smooth: { stiffness: 200, damping: 20 },
        responsive: { stiffness: 500, damping: 25, mass: 0.5 }
    },

    stagger: {
        fast: 0.05,
        normal: 0.1,
        slow: 0.15
    }
} as const;
