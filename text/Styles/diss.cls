%%---------------------------------------------------------------
%% Dokumentenklasse für VDI-kompatible Dissertationen sowie
%% Studien-, Projekt- und Diplomarbeiten am IfM und MZH 
%%---------------------------------------------------------------
%% $Id$
%%---------------------------------------------------------------
%% Diese Klasse basiert auf der Standard-Klasse "report.cls"
%% und enthält die Größenoption "size12.clo", eine Caption-
%% Formatierung sowie Erweiterungen für eine Quelltextstruktur
%% in Unterverzeichnissen
%%---------------------------------------------------------------
\NeedsTeXFormat{LaTeX2e}[1995/12/01]
%----------------------------------------------------------------
\ProvidesClass{Styles/diss_utf8}
  [2002/06/17 v2.1 LaTeX document class]
%----------------------------------------------------------------              
\newif\if@restonecol
\newif\if@openright
\newif\if@draft
%----------------------------------------------------------------
% Optionen deklarieren
%----------------------------------------------------------------
% einseitig (Standard) für DA, zweiseitig für Diss
\DeclareOption{oneside}{\@twosidefalse \@mparswitchfalse}
\DeclareOption{twoside}{\@twosidetrue  \@mparswitchtrue}
% openright fängt Kapitel immer auf rechter Seite an.
\DeclareOption{openright}{\@openrighttrue}
\DeclareOption{openany}{\@openrightfalse}
% twocolumn ist prinzipiell möglich, aber nicht sinnvoll
%\DeclareOption{onecolumn}{\@twocolumnfalse}
%\DeclareOption{twocolumn}{\@twocolumntrue}
% Bilder nicht suchen sondern einheitlich durch Box ersetzen
\DeclareOption{draft}{\@drafttrue}
\DeclareOption{final}{\@draftfalse}
% openbib formatiert die Literatur anders
% (evtl. für DAs geeignet)
\DeclareOption{openbib}{%
  \AtEndOfPackage{%
   \renewcommand\@openbib@code{%
      \advance\leftmargin\bibindent
      \itemindent -\bibindent
      \listparindent \itemindent
      \parsep \z@
      }%
   \renewcommand\newblock{\par}}%
}
\ExecuteOptions{oneside,openany,final}
\ProcessOptions
%----------------------------------------------------------------
% Schriftgrößen definieren
%----------------------------------------------------------------
%----------------------------------------------------------------
% Schriftgrößen definieren
%----------------------------------------------------------------
% Standard: 12 Punkt (18 Punkt Zeilenabstand)
\renewcommand\normalsize{%
   \@setfontsize\normalsize\@xiipt{18}%
   \abovedisplayskip 8\p@ \@plus3\p@
   \belowdisplayskip \abovedisplayskip
   \abovedisplayshortskip \z@ \@plus3\p@
   \belowdisplayshortskip \abovedisplayskip
   \let\@listi\@listI}
\normalsize
% Small: 11 Punkt (16 Punkt Abstand)
\newcommand\small{%
   \@setfontsize\small\@xipt{16}%
   \abovedisplayskip 6\p@ \@plus2\p@
   \belowdisplayskip \abovedisplayskip
   \abovedisplayshortskip \z@ \@plus2\p@
   \belowdisplayshortskip \abovedisplayskip
   \def\@listi{\leftmargin\leftmargini
               \topsep 9\p@ \@plus3\p@ \@minus5\p@
               \parsep 4.5\p@ \@plus2\p@ \@minus\p@
               \itemsep \parsep}%
}
\newcommand\footnotesize{%
   \@setfontsize\footnotesize\@xpt\@xiipt
   \abovedisplayskip 4\p@ \@plus1\p@
   \belowdisplayskip \abovedisplayskip
   \abovedisplayshortskip \z@ \@plus1\p@
   \belowdisplayshortskip \abovedisplayskip
   \def\@listi{\leftmargin\leftmargini
               \topsep 6\p@ \@plus2\p@ \@minus2\p@
               \parsep 3\p@ \@plus2\p@ \@minus\p@
               \itemsep \parsep}%
}
\newcommand\scriptsize{\@setfontsize\scriptsize\@viiipt{9.5}}
\newcommand\tiny{\@setfontsize\tiny\@vipt\@viipt}
\newcommand\large{\@setfontsize\large\@xivpt{18}}
\newcommand\Large{\@setfontsize\Large\@xviipt{22}}
\newcommand\LARGE{\@setfontsize\LARGE\@xxpt{25}}
\newcommand\huge{\@setfontsize\huge\@xxvpt{30}}
\let\Huge=\huge
%----------------------------------------------------------------
% Skips
%----------------------------------------------------------------
\setlength\smallskipamount{3\p@ \@plus 1\p@ \@minus 1\p@}
\setlength\medskipamount{6\p@ \@plus 2\p@ \@minus 2\p@}
\setlength\bigskipamount{12\p@ \@plus 4\p@ \@minus 4\p@}
%----------------------------------------------------------------
% Kopf- und Fußzeilenabstände
%----------------------------------------------------------------
\setlength\headheight{12\p@}
\setlength\headsep   {24\p@}
\setlength\topskip   {12\p@}
\setlength\footskip  {36\p@}
\setlength\maxdepth  {.5\topskip}
%----------------------------------------------------------------
% Papiergröße
%----------------------------------------------------------------
\hoffset-1in
\voffset-1in
\setlength\paperheight {297mm}
\setlength\paperwidth  {210mm}
%\setlength\paperheight {845\p@}
%\setlength\paperwidth  {598\p@}
\setlength\overfullrule{0\p@}
%----------------------------------------------------------------
% Textbreite und -höhe
%----------------------------------------------------------------
\setlength\textwidth{16.1cm}
%\setlength\textwidth{471\p@} % = 597-56-70 (!!)
\setlength\textheight{25cm}
%\setlength\textheight{694\p@}
%----------------------------------------------------------------
% Randkommentarbreite
%----------------------------------------------------------------
\setlength\marginparsep{3\p@}
\setlength\marginparpush{7\p@}
\setlength\marginparwidth{40\p@}
%----------------------------------------------------------------
% linke Seitenränder gerade und ungerade Seiten
%----------------------------------------------------------------
%\setlength\oddsidemargin{70\p@}
%\setlength\evensidemargin{56\p@}
\setlength\oddsidemargin{2.925cm}
\setlength\evensidemargin{1.975cm}
%----------------------------------------------------------------
% Oberer Seitenrand
%----------------------------------------------------------------
\setlength\topmargin{48\p@}
%----------------------------------------------------------------
% Diverse Abstände
%----------------------------------------------------------------
\setlength\footnotesep{8.4\p@}
\setlength{\skip\footins}{10.8\p@ \@plus 4\p@ \@minus 2\p@}
\setlength\floatsep    {4\p@ \@plus 2\p@ \@minus 2\p@}
\setlength\textfloatsep{4\p@ \@plus 2\p@ \@minus 2\p@}
\setlength\intextsep   {4\p@ \@plus 2\p@ \@minus 2\p@} % Intextsep war durch mich auf 10 gesetzt
\setlength\dblfloatsep    {4\p@ \@plus 2\p@ \@minus 2\p@}
\setlength\dbltextfloatsep{4\p@ \@plus 2\p@ \@minus 2\p@}
\setlength\@fptop{0\p@ \@plus 1fil}
\setlength\@fpsep{10\p@ \@plus 2fil}
\setlength\@fpbot{0\p@ \@plus 1fil}
\setlength\@dblfptop{0\p@ \@plus 1fil}
\setlength\@dblfpsep{10\p@ \@plus 2fil}
\setlength\@dblfpbot{0\p@ \@plus 1fil}
\setlength\partopsep{3\p@ \@plus 2\p@ \@minus 2\p@}
%----------------------------------------------------------------
% Listenabstände (Itemize etc.)
%----------------------------------------------------------------
\def\@listi{\leftmargin\leftmargini
%            \parsep 5\p@  \@plus2.5\p@ \@minus\p@
%            \topsep 10\p@ \@plus4\p@   \@minus6\p@
%            \itemsep5\p@  \@plus2.5\p@ \@minus\p@}
            \parsep \z@
            \topsep \z@
            \itemsep 6\p@}
\let\@listI\@listi
\@listi
\def\@listii {\leftmargin\leftmarginii
              \labelwidth\leftmarginii
              \advance\labelwidth-\labelsep
              \topsep    5\p@   \@plus2.5\p@ \@minus\p@
              \parsep    2.5\p@ \@plus\p@    \@minus\p@
              \itemsep   \parsep}
\def\@listiii{\leftmargin\leftmarginiii
              \labelwidth\leftmarginiii
              \advance\labelwidth-\labelsep
              \topsep    2.5\p@\@plus\p@\@minus\p@
              \parsep    \z@
              \partopsep \p@ \@plus\z@ \@minus\p@
              \itemsep   \topsep}
\def\@listiv {\leftmargin\leftmarginiv
              \labelwidth\leftmarginiv
              \advance\labelwidth-\labelsep}
\def\@listv  {\leftmargin\leftmarginv
              \labelwidth\leftmarginv
              \advance\labelwidth-\labelsep}
\def\@listvi {\leftmargin\leftmarginvi
              \labelwidth\leftmarginvi
              \advance\labelwidth-\labelsep}
%---------------------------------------------------------------
% Zeilenabstände
%---------------------------------------------------------------
\setlength\lineskip{0\p@}
\setlength\normallineskip{0\p@}
\renewcommand\baselinestretch{}
\setlength\parskip{8\p@ \@plus \p@}
\setlength\parindent{0\p@}
\@lowpenalty   51
\@medpenalty  151
\@highpenalty 301
%---------------------------------------------------------------
% Zähler für Float-Objekte
%---------------------------------------------------------------
\setcounter{topnumber}{1}
\renewcommand\topfraction{.7}
\setcounter{bottomnumber}{1}
\renewcommand\bottomfraction{.3}
\setcounter{totalnumber}{2}
\renewcommand\textfraction{.2}
\renewcommand\floatpagefraction{.5}
\setcounter{dbltopnumber}{2}
\renewcommand\dbltopfraction{.7}
\renewcommand\dblfloatpagefraction{.5}
%---------------------------------------------------------------
% Kopfzeilen
%---------------------------------------------------------------
\if@twoside
  \def\ps@headings{%
      \let\@oddfoot\@empty\let\@evenfoot\@empty
      \def\@evenhead{\thepage\hfil\slshape\leftmark}%
      \def\@oddhead{{\slshape\rightmark}\hfil\thepage}%
      \let\@mkboth\markboth
    \def\chaptermark##1{%
      \markboth {%
        \ifnum \c@secnumdepth >\m@ne
            \@chapapp\ \thechapter: \ %
        \fi
        ##1}{}}%
    \def\sectionmark##1{%
      \markright {%
        \ifnum \c@secnumdepth >\z@
          \thesection \ \ %
        \fi
        ##1}}}
\else
  \def\ps@headings{%
    \let\@oddfoot\@empty
    \def\@oddhead{{\slshape\rightmark}\hfil\thepage}%
    \let\@mkboth\markboth
    \def\chaptermark##1{%
      \markright {%
        \ifnum \c@secnumdepth >\m@ne
            \@chapapp\ \thechapter: \ %
        \fi
        ##1}}}
\fi
%---------------------------------------------------------------
% Kopfzeilen für erste Kapitelseite
%---------------------------------------------------------------
\if@twoside
  \def\ps@firsthead{%
      \let\@oddfoot\@empty
      \let\@evenfoot\@empty
      \def\@evenhead{\thepage}%
      \def\@oddhead{\hfil\thepage}}
\else
  \def\ps@firsthead{%
    \let\@oddfoot\@empty
    \def\@oddhead{\hfil\thepage}}
\fi
%---------------------------------------------------------------
% Titelseite
%---------------------------------------------------------------
\newcommand\maketitle{
  \begin{titlepage}
  \null\vfil
  \vskip 60\p@
  \begin{center}%
    \textbf{\Huge \@title \par}
    \vfill
    Dem Fachbereich Maschinenbau \\ 
    der Universität Hannover \\ 
    zur Erlangung des akademischen Grades \\ 
    Doktor-Ingenieur \\
    vorgelegte\\
    \vspace{2cm}
    Dissertation\\
    \vspace{2cm}
    von\\
    \vspace{3mm}
    \textbf{\@author}\\
    \vspace{1cm}
    \textbf{\@date}
  \end{center}
  \end{titlepage}%
  \global\let\maketitle\relax
  \global\let\@thanks\@empty
  \global\let\@author\@empty
  \global\let\@date\@empty
  \global\let\@title\@empty
  \global\let\thanks\relax
  \global\let\title\relax
  \global\let\author\relax
  \global\let\date\relax
  \global\let\and\relax 
}
%---------------------------------------------------------------
% Kapitelnumerierung
%---------------------------------------------------------------
\newcommand*\chaptermark[1]{}
\setcounter{secnumdepth}{2}
\newcounter {part}
\newcounter {chapter}
\newcounter {section}[chapter]
\newcounter {subsection}[section]
\newcounter {subsubsection}[subsection]
\newcounter {paragraph}[subsubsection]
\newcounter {subparagraph}[paragraph]
\renewcommand \thepart {\@Roman\c@part}
\renewcommand \thechapter {\@arabic\c@chapter}
\renewcommand \thesection {\thechapter.\@arabic\c@section}
\renewcommand\thesubsection   {\thesection.\@arabic\c@subsection}
\renewcommand\thesubsubsection{\thesubsection .\@arabic\c@subsubsection}
\renewcommand\theparagraph    {\thesubsubsection.\@arabic\c@paragraph}
\renewcommand\thesubparagraph {\theparagraph.\@arabic\c@subparagraph}
%---------------------------------------------------------------
% Definition: Part
%---------------------------------------------------------------
\newcommand\@chapapp{\chaptername}
\newcommand\part{%
  \if@openright
    \cleardoublepage
  \else
    \clearpage
  \fi
  \thispagestyle{firsthead}%
  \if@twocolumn
    \onecolumn
    \@tempswatrue
  \else
    \@tempswafalse
  \fi
  \null\vfil
  \secdef\@part\@spart}

\def\@part[#1]#2{%
    \ifnum \c@secnumdepth >-2\relax
      \refstepcounter{part}%
      \addcontentsline{toc}{part}{\thepart\hspace{1em}#1}%
    \else
      \addcontentsline{toc}{part}{#1}%
    \fi
    \markboth{}{}%
    {\centering
     \interlinepenalty \@M
     \normalfont
     \ifnum \c@secnumdepth >-2\relax
       \huge\bfseries \partname~\thepart
       \par
       \vskip 20\p@
     \fi
     \Huge \bfseries #2\par}%
    \@endpart}
\def\@spart#1{%
    {\centering
     \interlinepenalty \@M
     \normalfont
     \Huge \bfseries #1\par}%
    \@endpart}
\def\@endpart{\vfil\newpage
              \if@twoside
               \if@openright
                \null
                \thispagestyle{empty}%
                \newpage
               \fi
              \fi
              \if@tempswa
                \twocolumn
              \fi}
%---------------------------------------------------------------
% Definition: Chapter
%---------------------------------------------------------------
\newcommand\chapter{\if@openright
                      \cleardoublepage
                    \else
                      \clearpage
                    \fi
                    \thispagestyle{firsthead}%
                    \global\@topnum\z@
                    \@afterindentfalse
                    \secdef\@chapter\@schapter}
\def\@chapter[#1]#2{\ifnum \c@secnumdepth >\m@ne
                         \refstepcounter{chapter}%
                         \typeout{\@chapapp\space\thechapter.}%
                         \addcontentsline{toc}{chapter}%
                                   {\protect\numberline{\thechapter}#1}%
                    \else
                      \addcontentsline{toc}{chapter}{#1}%
                    \fi
                    \chaptermark{#1}%
                    \addtocontents{lof}{\protect\addvspace{10\p@}}%
                    \addtocontents{lot}{\protect\addvspace{10\p@}}%
                    \if@twocolumn
                      \@topnewpage[\@makechapterhead{#2}]%
                    \else
                      \@makechapterhead{#2}%
                      \@afterheading
                    \fi}
\def\@makechapterhead#1{%
  \vspace*{30\p@}%
  {\parindent \z@ \raggedright \normalfont
    \interlinepenalty\@M
    \huge \bfseries
    \ifnum \c@secnumdepth >\m@ne
        \thechapter \hspace{14pt}
    \fi
    #1\par\nobreak
    \vskip 40\p@
  }}
\def\@schapter#1{\if@twocolumn
                   \@topnewpage[\@makeschapterhead{#1}]%
                 \else
                   \@makeschapterhead{#1}%
                   \@afterheading
                 \fi}
\def\@makeschapterhead#1{%
  \vspace*{30\p@}%
  {\parindent \z@ \raggedright
    \normalfont
    \interlinepenalty\@M
    \huge \bfseries  #1\par\nobreak
    \vskip 40\p@
  }}
\newcommand\header[1]{
  \chapter*{#1}
  \addcontentsline{toc}{chapter}{#1}
%  \markboth{#1}{#1}
}
%---------------------------------------------------------------
% Definition: Section
%---------------------------------------------------------------
\newcommand\section{\@startsection {section}{1}{\z@}%
                                   {-3.5ex \@plus -1ex \@minus -.2ex}%
                                   {2.3ex \@plus.2ex}%
                                   {\normalfont\Large\bfseries}}
%---------------------------------------------------------------
% Definition: Subsection
%---------------------------------------------------------------
\newcommand\subsection{\@startsection{subsection}{2}{\z@}%
                                     {-3.25ex\@plus -1ex \@minus -.2ex}%
                                     {1.5ex \@plus .2ex}%
                                     {\normalfont\large\bfseries}}
%---------------------------------------------------------------
% Definition: Subsubsection
%---------------------------------------------------------------
\newcommand\subsubsection{\@startsection{subsubsection}{3}{\z@}%
                                     {-3.25ex\@plus -1ex \@minus -.2ex}%
                                     {1.5ex \@plus .2ex}%
                                     {\normalfont\normalsize\bfseries}}
%---------------------------------------------------------------
% Definition: Paragraph
%---------------------------------------------------------------
\newcommand\paragraph{\@startsection{paragraph}{4}{\z@}%
                                    {1ex \@plus1ex \@minus.2ex}%
                                    {-0.5em}%
                                    {\normalfont\normalsize\bfseries}}
%---------------------------------------------------------------
% Definition: Subparagraph
%---------------------------------------------------------------
\newcommand\subparagraph{\@startsection{subparagraph}{5}{\parindent}%
                                       {0ex}
                                       {-0.5em}%
                                      {\normalfont\normalsize\bfseries}}
%---------------------------------------------------------------
% Seitenränder für Listen
%---------------------------------------------------------------
\if@twocolumn
  \setlength\leftmargini  {2em}
\else
  \setlength\leftmargini  {2.5em}
\fi
\leftmargin  \leftmargini
\setlength\leftmarginii  {2.2em}
\setlength\leftmarginiii {1.87em}
\setlength\leftmarginiv  {1.7em}
\if@twocolumn
  \setlength\leftmarginv  {.5em}
  \setlength\leftmarginvi {.5em}
\else
  \setlength\leftmarginv  {1em}
  \setlength\leftmarginvi {1em}
\fi
\setlength  \labelsep  {.5em}
\setlength  \labelwidth{\leftmargini}
\addtolength\labelwidth{-\labelsep}
\@beginparpenalty -\@lowpenalty
\@endparpenalty   -\@lowpenalty
\@itempenalty     -\@lowpenalty
%---------------------------------------------------------------
% Listennumerierung
%---------------------------------------------------------------
\renewcommand\theenumi{\@arabic\c@enumi}
\renewcommand\theenumii{\@alph\c@enumii}
\renewcommand\theenumiii{\@roman\c@enumiii}
\renewcommand\theenumiv{\@Alph\c@enumiv}
\newcommand\labelenumi{\theenumi.}
\newcommand\labelenumii{(\theenumii)}
\newcommand\labelenumiii{\theenumiii.}
\newcommand\labelenumiv{\theenumiv.}
\renewcommand\p@enumii{\theenumi}
\renewcommand\p@enumiii{\theenumi(\theenumii)}
\renewcommand\p@enumiv{\p@enumiii\theenumiii}
\newcommand\labelitemi{\textbullet}
\newcommand\labelitemii{\normalfont\bfseries \textendash}
\newcommand\labelitemiii{\textasteriskcentered}
\newcommand\labelitemiv{\textperiodcentered}
\newenvironment{description}
               {\list{}{\labelwidth\z@ \itemindent-\leftmargin
                        \let\makelabel\descriptionlabel}}
               {\endlist}
\newcommand*\descriptionlabel[1]{\hspace\labelsep
                                \normalfont\bfseries #1}
%---------------------------------------------------------------
% Umgebung: Quotation
%---------------------------------------------------------------
\newenvironment{quotation}
               {\list{}{\listparindent 1.5em%
                        \itemindent    \listparindent
                        \rightmargin   \leftmargin
                        \parsep        \z@ \@plus\p@}%
                \item\relax}
               {\endlist}
%---------------------------------------------------------------
% Umgebung: Quote
%---------------------------------------------------------------
\newenvironment{quote}
               {\list{}{\rightmargin\leftmargin}%
                \item\relax}
               {\endlist}
%---------------------------------------------------------------
% Umgebung: Titlepage
%---------------------------------------------------------------
\newenvironment{titlepage}
    {%
      \if@twocolumn
        \@restonecoltrue\onecolumn
      \else
        \@restonecolfalse\newpage
      \fi
      \thispagestyle{empty}%
      \setcounter{page}\@ne
    }%
    {\if@restonecol\twocolumn \else \newpage \fi
     \if@twoside\else
        \setcounter{page}\@ne
     \fi
    }
%---------------------------------------------------------------
% Umgebung: Appendix
%---------------------------------------------------------------
\newcommand\appendix{\par
  \setcounter{chapter}{0}%
  \setcounter{section}{0}%
  \gdef\@chapapp{\appendixname}%
  \gdef\thechapter{\@Alph\c@chapter}}
%---------------------------------------------------------------
% Abstände für Arrays und Tables
%---------------------------------------------------------------
\setlength\arraycolsep{5\p@}
\setlength\tabcolsep{6\p@}
\setlength\arrayrulewidth{.4\p@}
\setlength\doublerulesep{2\p@}
\setlength\tabbingsep{\labelsep}
\skip\@mpfootins = \skip\footins
\setlength\fboxsep{3\p@}
\setlength\fboxrule{.4\p@}
%---------------------------------------------------------------
% Numerierung: Equation
%---------------------------------------------------------------
\@addtoreset {equation}{chapter}
\renewcommand\theequation
  {\ifnum \c@chapter>\z@ \thechapter.\fi \@arabic\c@equation}
%---------------------------------------------------------------
% Numerierung: Figure
%---------------------------------------------------------------
\newcounter{figure}[chapter]
\renewcommand \thefigure
     {\ifnum \c@chapter>\z@ \thechapter.\fi \@arabic\c@figure}
\def\fps@figure{tbp}
\def\ftype@figure{1}
\def\ext@figure{lof}
\def\fnum@figure{\figurename~\thefigure}
\newenvironment{figure}
               {\@float{figure}}
               {\end@float}
\newenvironment{figure*}
               {\@dblfloat{figure}}
               {\end@dblfloat}
%---------------------------------------------------------------
% Numerierung: Table
%---------------------------------------------------------------
\newcounter{table}[chapter]
\renewcommand \thetable
     {\ifnum \c@chapter>\z@ \thechapter.\fi \@arabic\c@table}
\def\fps@table{tbp}
\def\ftype@table{2}
\def\ext@table{lot}
\def\fnum@table{\tablename~\thetable}
\newenvironment{table}
               {\@float{table}}
               {\end@float}
\newenvironment{table*}
               {\@dblfloat{table}}
               {\end@dblfloat}
%---------------------------------------------------------------
% Captions (aus dem Caption-Package, bf, isu, nooneline)
%---------------------------------------------------------------
\newlength\abovecaptionskip
\newlength\belowcaptionskip
\setlength\abovecaptionskip{4\p@}
\setlength\belowcaptionskip{4\p@}
\newlength\captionmargin
\setlength\captionmargin{0\p@}
\newsavebox{\as@captionbox}
\newlength{\as@captionwidth}
\newcommand{\as@isucaption}[2]{
  \sbox{\as@captionbox}{#1\space}
  \addtolength{\as@captionwidth}{-\wd\as@captionbox}
  \usebox{\as@captionbox}\parbox[t]{\as@captionwidth}{\leavevmode#2}}
\newcommand{\as@makecaption}[2]{
  \setlength{\leftskip}{\captionmargin}
  \setlength{\rightskip}{\captionmargin}
  \addtolength{\as@captionwidth}{-2\captionmargin}
  \as@isucaption{\textbf{#1:}}{#2}}
\newcommand{\@makecaption}[2]{
  \vskip\abovecaptionskip
  \setlength{\as@captionwidth}{\linewidth}
  \as@makecaption{#1}{#2}
  \vskip\belowcaptionskip}
%---------------------------------------------------------------
% Alte Schriftkommandos
%---------------------------------------------------------------
\DeclareOldFontCommand{\rm}{\normalfont\rmfamily}{\mathrm}
\DeclareOldFontCommand{\sf}{\normalfont\sffamily}{\mathsf}
\DeclareOldFontCommand{\tt}{\normalfont\ttfamily}{\mathtt}
\DeclareOldFontCommand{\bf}{\normalfont\bfseries}{\mathbf}
\DeclareOldFontCommand{\it}{\normalfont\itshape}{\mathit}
\DeclareOldFontCommand{\sl}{\normalfont\slshape}{\@nomath\sl}
\DeclareOldFontCommand{\sc}{\normalfont\scshape}{\@nomath\sc}
\DeclareRobustCommand*\cal{\@fontswitch\relax\mathcal}
\DeclareRobustCommand*\mit{\@fontswitch\relax\mathnormal}
%---------------------------------------------------------------
% Inhaltsverzeichnis
%---------------------------------------------------------------
\newcommand\@pnumwidth{1.55em}
\newcommand\@tocrmarg{2.55em}
\newcommand\@dotsep{4.5}
\newlength\@docparskip
\newlength\tocparskip
\setlength\tocparskip{0\p@}
\setcounter{tocdepth}{2}
\newcommand\tableofcontents{%
    \if@twocolumn
      \@restonecoltrue\onecolumn
    \else
      \@restonecolfalse
    \fi
    \chapter*{\contentsname
        \@mkboth{%
           \contentsname}{\contentsname}}%
    \setlength\@docparskip\parskip
    \setlength\parskip\tocparskip
    \@starttoc{toc}%
    \setlength\parskip\@docparskip
    \if@restonecol\twocolumn\fi
    }
\newcommand*\l@part[2]{%
  \ifnum \c@tocdepth >-2\relax
    \addpenalty{-\@highpenalty}%
    \addvspace{2.25em \@plus\p@}%
    \begingroup
      \parindent \z@ \rightskip \@pnumwidth
      \parfillskip -\@pnumwidth
      {\leavevmode
       \large \bfseries #1\hfil \hb@xt@\@pnumwidth{\hss #2}}\par
       \nobreak
         \global\@nobreaktrue
         \everypar{\global\@nobreakfalse\everypar{}}%
    \endgroup
  \fi}
\newcommand*\l@chapter[2]{%
  \ifnum \c@tocdepth >\m@ne
    \addpenalty{-\@highpenalty}%
    \vskip 1.0em \@plus\p@
    \setlength\@tempdima{1.5em}%
    \begingroup
      \parindent \z@ \rightskip \@pnumwidth
      \parfillskip -\@pnumwidth
      \leavevmode \bfseries
      \advance\leftskip\@tempdima
      \hskip -\leftskip
      #1\nobreak\hfil \nobreak\hb@xt@\@pnumwidth{\hss #2}\par
      \penalty\@highpenalty
    \endgroup
  \fi}
\newcommand*\l@section{\@dottedtocline{1}{1.5em}{2.3em}}
\newcommand*\l@subsection{\@dottedtocline{2}{3.8em}{3.2em}}
\newcommand*\l@subsubsection{\@dottedtocline{3}{7.0em}{4.1em}}
\newcommand*\l@paragraph{\@dottedtocline{4}{10em}{5em}}
\newcommand*\l@subparagraph{\@dottedtocline{5}{12em}{6em}}
%---------------------------------------------------------------
% Figure-Verzeichnis
%---------------------------------------------------------------
\newcommand\listoffigures{%
    \if@twocolumn
      \@restonecoltrue\onecolumn
    \else
      \@restonecolfalse
    \fi
    \chapter*{\listfigurename
      \@mkboth{\listfigurename}%
              {\listfigurename}}%
    \@starttoc{lof}%
    \if@restonecol\twocolumn\fi
    }
\newcommand*\l@figure{\@dottedtocline{1}{1.5em}{2.3em}}
%---------------------------------------------------------------
% Table-Verzeichnis
%---------------------------------------------------------------
\newcommand\listoftables{%
    \if@twocolumn
      \@restonecoltrue\onecolumn
    \else
      \@restonecolfalse
    \fi
    \chapter*{\listtablename
      \@mkboth{%
          \listtablename}{\listtablename}}%
    \@starttoc{lot}%
    \if@restonecol\twocolumn\fi
    }
\let\l@table\l@figure
%---------------------------------------------------------------
% Literaturverzeichnis
%---------------------------------------------------------------
\newdimen\bibindent
\setlength\bibindent{1.5em}
\newenvironment{thebibliography}[1]{
  \chapter*{\bibname \@mkboth{\bibname}{\bibname}}%
  \addcontentsline{toc}{chapter}{\bibname}
  \list{\@biblabel{\@arabic\c@enumiv}}%
   {\settowidth\labelwidth{\@biblabel{#1}}%
    \leftmargin\labelwidth
    \advance\leftmargin\labelsep
    \@openbib@code
    \usecounter{enumiv}%
    \let\p@enumiv\@empty
    \renewcommand\theenumiv{\@arabic\c@enumiv}}%
  \sloppy
  \clubpenalty4000
  \@clubpenalty \clubpenalty
  \widowpenalty4000%
  \sfcode`\.\@m}
   {\def\@noitemerr
     {\@latex@warning{Empty `thebibliography' environment}}%
    \endlist}
\newcommand\newblock{\hskip .11em\@plus.33em\@minus.07em}
\let\@openbib@code\@empty
%---------------------------------------------------------------
% Index
%---------------------------------------------------------------
\newenvironment{theindex}
               {\if@twocolumn
                  \@restonecolfalse
                \else
                  \@restonecoltrue
                \fi
                \columnseprule \z@
                \columnsep 35\p@
                \twocolumn[\@makeschapterhead{\indexname}]%
                \@mkboth{\indexname}%
                        {\indexname}%
                \thispagestyle{plain}\parindent\z@
                \parskip\z@ \@plus .3\p@\relax
                \let\item\@idxitem}
               {\if@restonecol\onecolumn\else\clearpage\fi}
\newcommand\@idxitem{\par\hangindent 40\p@}
\newcommand\subitem{\@idxitem \hspace*{20\p@}}
\newcommand\subsubitem{\@idxitem \hspace*{30\p@}}
\newcommand\indexspace{\par \vskip 10\p@ \@plus5\p@ \@minus3\p@\relax}
%---------------------------------------------------------------
% Fußnotenlinie neu definieren
%---------------------------------------------------------------
\renewcommand\footnoterule{%
  \kern-3\p@
  \hrule\@width.4\columnwidth
  \kern2.6\p@}
\@addtoreset{footnote}{chapter}
%---------------------------------------------------------------
% ???
%---------------------------------------------------------------
\newcommand\@makefntext[1]{%
    \parindent 1em%
    \noindent
    \hb@xt@1.8em{\hss\@makefnmark}#1}
%---------------------------------------------------------------
% Diverse Texte (werden von ngerman.sty überschrieben!)
%---------------------------------------------------------------
\newcommand\contentsname{Contents}
\newcommand\listfigurename{List of Figures}
\newcommand\listtablename{List of Tables}
\newcommand\bibname{Bibliography}
\newcommand\indexname{Index}
\newcommand\figurename{Figure}
\newcommand\tablename{Table}
\newcommand\partname{Part}
\newcommand\chaptername{Chapter}
\newcommand\appendixname{Appendix}
\newcommand\abstractname{Abstract}
\def\today{\ifcase\month\or
  January\or February\or March\or April\or May\or June\or
  July\or August\or September\or October\or November\or December\fi
  \space\number\day, \number\year}
%---------------------------------------------------------------
% Seite einrichten
%---------------------------------------------------------------
\pagestyle{headings}
\pagenumbering{arabic}
\flushbottom
\sloppy
%---------------------------------------------------------------
% Definitionen für Unterverzeichnisstruktur
%---------------------------------------------------------------
% Name des aktuellen Unterverzeichnisses
\newcommand\chaptersubdir{}
% Kapiteldatei aus Unterverzeichnis einbinden
\newcommand\includefile[2]{
 \renewcommand{\chaptersubdir}{#1}
 \input{#1/#2}
}
%---------------------------------------------------------------
% Einbindung von Abbildungen auf einen Befehl reduzieren
%---------------------------------------------------------------
% 1. Parameter: Optionale Position (Default: htb)
% 2. Parameter: Dateiname (ohne Endung), wird mit fig: davor 
%               automatisch zum label. 
% 3. Parameter: Bildunterschrift
% Lädt das Bild aus dem Unterverzeichnis mit dem Bildnamen im 
% aktuellen Unterverzeichnis \chaptersubdir
%---------------------------------------------------------------
\newcommand{\includefigure}[3][htb]{
 \begin{figure}[#1]
 \begin{center}
 \includegraphics{\chaptersubdir/#2/#2}
 \caption{#3}
 \label{fig:#2}
 \end{center}
\end{figure}
}
% \abbildung nur als alias definieren (Kompatibilität!)
\newcommand{\abbildung}[3][htb]{
 \includefigure[#1]{#2}{#3}
}

\newcommand{\includescaledfigure}[3][htb]{
 \begin{figure}[#1]
 \begin{center}
 \includegraphics[width=0.6\textwidth]{\chaptersubdir/#2/#2}
 \caption{#3}
 \label{fig:#2}
 \end{center}
\end{figure}
}


% \abbildung nur als alias definieren (Kompatibilität!)
\newcommand{\abbildungscaled}[3][htb]{
 \includescaledfigure[#1]{#2}{#3}
}

\newcommand{\includetextwidthfigure}[3][htb]{
 \begin{figure}[#1]
 \begin{center}
 \includegraphics[width=\textwidth]{\chaptersubdir/#2/#2}
 \caption{#3}
 \label{fig:#2}
 \end{center}
\end{figure}
}
% \abbildung nur als alias definieren (Kompatibilität!)
\newcommand{\abbildungtextwidth}[3][htb]{
 \includetextwidthfigure[#1]{#2}{#3}
}
%---------------------------------------------------------------
% Dateiende
%---------------------------------------------------------------
\endinput
%%
%% End of file `diss.cls'.
