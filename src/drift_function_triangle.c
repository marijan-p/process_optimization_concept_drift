/*-------------------------------------------------------------------------
-            d r i f t _ f u n c t i o n _ t r i a n g l e . c          -
---------------------------------------------------------------------------
  Dreieck-Driftsignal als Alternative zum Saegezahn (drift_function_sawtooth.c),
  falls der TEP auf die Sudden Drifts der Saegezahnfunktion zu sensibel
  reagiert: rein inkrementeller Drift ohne Spruenge, deterministisch.

  Austausch gegen den Saegezahn ausschliesslich ueber die #include-Zeile
  in temexd_mod_drift.c:
    #include "drift_function_sawtooth.c"           -> Saegezahn
    #include "drift_function_triangle.c"  -> Dreieck

  Identische Signatur wie der Saegezahn; gamma und seed werden nicht
  benoetigt und ignoriert. Rueckgabewert normiert auf [-1, 1], die
  Amplitude skaliert der Aufrufer (IDV(29)-Wert). Start bei c(0) = 0 auf
  fallender Flanke; Flankendauer = period (gleiche Steigungsbetraege wie
  ein Saegezahn-Segment voller Hoehe).

  Parameter:
    t       Zeit seit Drift-Aktivierung in h (t <= 0 -> 0)
    period  Flankendauer in h
    gamma   ignoriert (Signaturkompatibilitaet)
    seed    ignoriert (Signaturkompatibilitaet)

  Kompilierung als Shared Library:  -DDRIFT_BUILD_DLL
-------------------------------------------------------------------------*/

#include <math.h>

#if defined(DRIFT_BUILD_DLL) && defined(_WIN32)
#define DRIFT_API __declspec(dllexport)
#else
#define DRIFT_API
#endif
#define CD_MID 0.0  /* (c_min + c_max)/2 */
#define CD_HALF 0.5 /* (c_max - c_min)/2 */

DRIFT_API double drift_signal(double t, double period, double gamma,
                              unsigned long long seed)
{
  double tau;

  (void)gamma;
  (void)seed;

  if (t <= 0.0 || period <= 0.0)
  {
    return 0.0;
  }

  /* Phase so verschoben, dass c(0) = 0 auf der fallenden Flanke liegt */
  tau = fmod(t + 0.5 * period, 2.0 * period);
  if (tau < period)
  {
    return CD_MID + CD_HALF * (1.0 - 2.0 * tau / period);
  }
  return CD_MID + CD_HALF * (-1.0 + 2.0 * (tau - period) / period);
}
