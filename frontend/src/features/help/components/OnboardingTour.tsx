/**
 * Onboarding Tour - Stepped Tour durch die App
 */

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import {
  useCompleteOnboardingStep,
  useOnboardingStatus,
  useSkipOnboarding,
} from '../hooks/useHelp';

interface OnboardingTourProps {
  autoStart?: boolean;
}

export function OnboardingTour({ autoStart = true }: OnboardingTourProps) {
  const [isActive, setIsActive] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  const { data: status, isLoading } = useOnboardingStatus();
  const completeStep = useCompleteOnboardingStep();
  const skipOnboarding = useSkipOnboarding();

  // Auto-start wenn noch nicht abgeschlossen
  useEffect(() => {
    if (autoStart && status && !status.completed && !isLoading) {
      setIsActive(true);
      // Setze auf den aktuellen Schritt falls Tour unterbrochen wurde
      if (status.current_step !== null) {
        setCurrentStepIndex(status.current_step);
      }
    }
  }, [autoStart, status, isLoading]);

  if (isLoading || !status || status.completed || !isActive) {
    return null;
  }

  const steps = [
    {
      id: 'welcome',
      title: 'Willkommen im Ablage-System!',
      description:
        'In dieser kurzen Tour zeigen wir Ihnen die wichtigsten Funktionen.',
      targetElement: null,
    },
    {
      id: 'upload',
      title: 'Dokumente hochladen',
      description:
        'Laden Sie Dokumente per Drag & Drop oder über den Upload-Button hoch. Das System erkennt automatisch den Dokumenttyp.',
      targetElement: '[data-tour="upload-button"]',
    },
    {
      id: 'ocr',
      title: 'OCR-Verarbeitung',
      description:
        'Nach dem Upload wird automatisch eine OCR-Texterkennung durchgeführt. Sie können zwischen verschiedenen Backends wählen.',
      targetElement: '[data-tour="ocr-settings"]',
    },
    {
      id: 'folders',
      title: 'Ordner-Struktur',
      description:
        'Organisieren Sie Ihre Dokumente in Ordnern. Nutzen Sie die Kategorien für bessere Übersicht.',
      targetElement: '[data-tour="folder-tree"]',
    },
    {
      id: 'search',
      title: 'Volltextsuche',
      description:
        'Durchsuchen Sie alle Dokumente mit der leistungsstarken Volltextsuche. Auch in gescannten Dokumenten!',
      targetElement: '[data-tour="search-bar"]',
    },
    {
      id: 'complete',
      title: 'Tour abgeschlossen!',
      description:
        'Sie können jederzeit über den Hilfe-Button (unten rechts) weitere Informationen abrufen.',
      targetElement: null,
    },
  ];

  const currentStep = steps[currentStepIndex];
  const progress = ((currentStepIndex + 1) / steps.length) * 100;

  const handleNext = async () => {
    // Schritt als abgeschlossen markieren
    await completeStep.mutateAsync(currentStep.id);

    if (currentStepIndex < steps.length - 1) {
      setCurrentStepIndex(currentStepIndex + 1);
    } else {
      setIsActive(false);
    }
  };

  const handlePrevious = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  };

  const handleSkip = async () => {
    await skipOnboarding.mutateAsync();
    setIsActive(false);
  };

  // Spotlight-Effekt für aktuelles Element
  useEffect(() => {
    if (currentStep.targetElement) {
      const element = document.querySelector(currentStep.targetElement);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        element.classList.add('tour-spotlight');
      }
    }

    return () => {
      // Cleanup
      if (currentStep.targetElement) {
        const element = document.querySelector(currentStep.targetElement);
        if (element) {
          element.classList.remove('tour-spotlight');
        }
      }
    };
  }, [currentStep]);

  return (
    <>
      {/* Overlay */}
      <div className="fixed inset-0 bg-black/50 z-50 backdrop-blur-sm" />

      {/* Tour Card */}
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-md">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <CardTitle>{currentStep.title}</CardTitle>
                <CardDescription>
                  Schritt {currentStepIndex + 1} von {steps.length}
                </CardDescription>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSkip}
                className="h-8 w-8 p-0"
              >
                <X className="h-4 w-4" />
                <span className="sr-only">Tour beenden</span>
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {currentStep.description}
            </p>

            <Progress value={progress} />
          </CardContent>

          <CardFooter className="flex justify-between">
            <Button
              variant="outline"
              onClick={handlePrevious}
              disabled={currentStepIndex === 0}
            >
              <ChevronLeft className="h-4 w-4 mr-2" />
              Zurück
            </Button>

            <Button onClick={handleNext} disabled={completeStep.isPending}>
              {currentStepIndex === steps.length - 1 ? (
                'Abschließen'
              ) : (
                <>
                  Weiter
                  <ChevronRight className="h-4 w-4 ml-2" />
                </>
              )}
            </Button>
          </CardFooter>
        </Card>
      </div>

      {/* CSS für Spotlight-Effekt */}
      <style>{`
        .tour-spotlight {
          position: relative;
          z-index: 51;
          box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);
          border-radius: 0.5rem;
        }
      `}</style>
    </>
  );
}
