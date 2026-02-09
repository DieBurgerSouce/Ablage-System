/**
 * MerkleProofViewer - Kryptografischer Beweis-Viewer
 *
 * Zeigt Merkle Proof als vertikale Kette mit Verifikations-Status.
 * Wird als Dialog dargestellt.
 */

import { useState } from "react";
import {
  CheckCircle,
  XCircle,
  Copy,
  Link2,
  Loader2,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import {
  useMerkleProof,
  useVerifyProof,
  type MerkleProof,
} from "../api/audit-chain-api";

// =============================================================================
// Hash Display Helper
// =============================================================================

function TruncatedHash({
  hash,
  label,
}: {
  hash: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      {label && (
        <span className="text-xs text-muted-foreground font-medium">
          {label}:
        </span>
      )}
      <code className="text-xs font-mono bg-muted px-2 py-1 rounded">
        {hash.substring(0, 12)}...{hash.substring(hash.length - 8)}
      </code>
      <Button
        variant="ghost"
        size="sm"
        className="h-6 w-6 p-0"
        onClick={handleCopy}
        aria-label="Hash kopieren"
      >
        {copied ? (
          <CheckCircle className="h-3 w-3 text-green-500" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </Button>
    </div>
  );
}

// =============================================================================
// Proof Path Visualization
// =============================================================================

function ProofPathChain({ proof }: { proof: MerkleProof }) {
  return (
    <div className="space-y-2">
      {/* Root Hash */}
      <div className="flex items-center gap-3 p-3 bg-primary/5 border border-primary/20 rounded-lg">
        <ShieldCheck className="h-5 w-5 text-primary flex-shrink-0" />
        <div>
          <p className="text-xs font-medium text-primary">Root Hash</p>
          <TruncatedHash hash={proof.root_hash} />
        </div>
      </div>

      {/* Proof Path */}
      {proof.proof_path.map((node, index) => (
        <div key={index} className="flex items-stretch gap-3">
          {/* Connector Line */}
          <div className="flex flex-col items-center w-5 flex-shrink-0">
            <div className="w-px h-2 bg-border" />
            <Link2 className="h-3 w-3 text-muted-foreground flex-shrink-0" />
            <div className="w-px flex-1 bg-border" />
          </div>

          {/* Node */}
          <div className="flex-1 p-3 border rounded-lg bg-card">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground">
                Ebene {proof.proof_path.length - index}
              </span>
              <Badge variant="outline" className="text-xs">
                {node.position === "left" ? "Links" : "Rechts"}
              </Badge>
            </div>
            <TruncatedHash hash={node.hash} />
          </div>
        </div>
      ))}

      {/* Entry Hash */}
      <div className="flex items-stretch gap-3">
        <div className="flex flex-col items-center w-5 flex-shrink-0">
          <div className="w-px h-2 bg-border" />
          <Link2 className="h-3 w-3 text-muted-foreground flex-shrink-0" />
        </div>
        <div className="flex-1 p-3 bg-muted/50 border rounded-lg">
          <p className="text-xs font-medium text-muted-foreground mb-1">
            Eintrag Hash
          </p>
          <TruncatedHash hash={proof.entry_hash} />
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

interface MerkleProofViewerProps {
  entryHash: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MerkleProofViewer({
  entryHash,
  open,
  onOpenChange,
}: MerkleProofViewerProps) {
  const { data: proof, isLoading, error } = useMerkleProof(entryHash);
  const verifyMutation = useVerifyProof();

  const handleVerify = () => {
    if (!proof) return;
    verifyMutation.mutate({
      entry_hash: proof.entry_hash,
      root_hash: proof.root_hash,
      proof_path: proof.proof_path,
    });
  };

  const isVerified = verifyMutation.data?.verified;
  const hasVerified = verifyMutation.isSuccess;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            Merkle Proof
          </DialogTitle>
          <DialogDescription>
            Kryptografischer Beweis der Eintrag-Integritaet
          </DialogDescription>
        </DialogHeader>

        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">
              Lade Beweis...
            </span>
          </div>
        )}

        {error && (
          <div className="py-6 text-center">
            <XCircle className="h-8 w-8 text-destructive mx-auto mb-2" />
            <p className="text-sm text-destructive">
              Beweis konnte nicht geladen werden.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Der Eintrag existiert moeglicherweise nicht in der Chain.
            </p>
          </div>
        )}

        {proof && (
          <div className="space-y-4">
            {/* Verification Status */}
            {hasVerified && (
              <div
                className={`flex items-center gap-2 p-3 rounded-lg ${
                  isVerified
                    ? "bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800"
                    : "bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800"
                }`}
              >
                {isVerified ? (
                  <>
                    <CheckCircle className="h-5 w-5 text-green-600" />
                    <div>
                      <p className="text-sm font-medium text-green-700 dark:text-green-300">
                        Gueltig
                      </p>
                      <p className="text-xs text-green-600 dark:text-green-400">
                        Der Beweis ist kryptografisch verifiziert.
                      </p>
                    </div>
                  </>
                ) : (
                  <>
                    <XCircle className="h-5 w-5 text-red-600" />
                    <div>
                      <p className="text-sm font-medium text-red-700 dark:text-red-300">
                        Ungueltig
                      </p>
                      <p className="text-xs text-red-600 dark:text-red-400">
                        Der Beweis konnte nicht verifiziert werden.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Proof Path Visualization */}
            <ProofPathChain proof={proof} />

            {/* Verify Button */}
            <Button
              onClick={handleVerify}
              disabled={verifyMutation.isPending}
              className="w-full"
            >
              {verifyMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifiziere...
                </>
              ) : hasVerified ? (
                "Erneut verifizieren"
              ) : (
                "Beweis verifizieren"
              )}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
