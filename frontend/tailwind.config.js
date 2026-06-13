import tailwindcssAnimate from "tailwindcss-animate"

/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ["class"],
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
    	extend: {
    		fontFamily: {
    			display: [
    				'Clash Display',
    				'sans-serif'
    			],
    			body: [
    				'Satoshi',
    				'sans-serif'
    			],
    			data: [
    				'Plus Jakarta Sans',
    				'sans-serif'
    			]
    		},
    		colors: {
    			border: 'hsl(var(--border))',
    			input: 'hsl(var(--input))',
    			ring: 'hsl(var(--ring))',
    			background: 'var(--background)',
    			foreground: 'var(--foreground)',
    			primary: {
    				DEFAULT: 'var(--primary)',
    				foreground: 'var(--primary-foreground)'
    			},
    			secondary: {
    				DEFAULT: 'var(--secondary)',
    				foreground: 'var(--secondary-foreground)'
    			},
    			destructive: {
    				DEFAULT: 'var(--destructive)',
    				foreground: 'var(--destructive-foreground)'
    			},
    			muted: {
    				DEFAULT: 'var(--muted)',
    				foreground: 'var(--muted-foreground)'
    			},
    			accent: {
    				DEFAULT: 'var(--accent)',
    				foreground: 'var(--accent-foreground)'
    			},
    			popover: {
    				DEFAULT: 'var(--popover)',
    				foreground: 'var(--popover-foreground)'
    			},
    			card: {
    				DEFAULT: 'var(--card)',
    				foreground: 'var(--card-foreground)'
    			},
    			sidebar: {
    				DEFAULT: 'var(--sidebar)',
    				foreground: 'var(--sidebar-foreground)',
    				'muted-foreground': 'var(--sidebar-muted-foreground)',
    				primary: 'var(--sidebar-primary)',
    				'primary-foreground': 'var(--sidebar-primary-foreground)',
    				accent: 'var(--sidebar-accent)',
    				'accent-foreground': 'var(--sidebar-accent-foreground)',
    				border: 'var(--sidebar-border)',
    				ring: 'var(--sidebar-ring)'
    			},
    			chart: {
    				'1': 'var(--chart-1)',
    				'2': 'var(--chart-2)',
    				'3': 'var(--chart-3)',
    				'4': 'var(--chart-4)',
    				'5': 'var(--chart-5)'
    			},
    			warning: 'var(--warning)',
    			success: 'var(--success)'
    		},
    		borderRadius: {
    			lg: 'var(--radius)',
    			md: 'calc(var(--radius) - 2px)',
    			sm: 'calc(var(--radius) - 4px)'
    		},
    		keyframes: {
    			'accordion-down': {
    				from: {
    					height: '0'
    				},
    				to: {
    					height: 'var(--radix-accordion-content-height)'
    				}
    			},
    			'accordion-up': {
    				from: {
    					height: 'var(--radix-accordion-content-height)'
    				},
    				to: {
    					height: '0'
    				}
    			},
    			'wiggle': {
    				'0%, 100%': { transform: 'rotate(-3deg)' },
    				'50%': { transform: 'rotate(3deg)' }
    			}
    		},
    		animation: {
    			'accordion-down': 'accordion-down 0.2s ease-out',
    			'accordion-up': 'accordion-up 0.2s ease-out',
    			'wiggle': 'wiggle 0.5s ease-in-out'
    		},
    		// WCAG 2.1 AA Touch Targets (min 44x44px)
    		minHeight: {
    			'touch': '44px',
    			'touch-lg': '48px',
    			'touch-xl': '56px'
    		},
    		minWidth: {
    			'touch': '44px',
    			'touch-lg': '48px',
    			'touch-xl': '56px'
    		},
    		// Safe area insets for mobile devices with notch/home indicator
    		padding: {
    			'safe-top': 'env(safe-area-inset-top)',
    			'safe-bottom': 'env(safe-area-inset-bottom)',
    			'safe-left': 'env(safe-area-inset-left)',
    			'safe-right': 'env(safe-area-inset-right)'
    		},
    		margin: {
    			'safe-top': 'env(safe-area-inset-top)',
    			'safe-bottom': 'env(safe-area-inset-bottom)',
    			'safe-left': 'env(safe-area-inset-left)',
    			'safe-right': 'env(safe-area-inset-right)'
    		}
    	}
    },
    plugins: [tailwindcssAnimate],
}
