/// P01 — Splash y onboarding.
///
/// Dos estados en una sola pantalla, como pide la ficha del documento de UX:
///
/// - **Splash** mientras la sesión arranca ([FaseSesion.arrancando]): emblema,
///   nombre del Reino y una línea de la voz del Reino. Si hay tokens válidos
///   dura menos de un segundo y el enrutador se lleva al usuario a Inicio.
/// - **Onboarding** de tres tarjetas deslizables que cuentan la promesa en
///   menos de treinta segundos, con "Saltar" siempre a mano y "Ya tengo
///   cuenta" para quien vuelve.
///
/// Solo se ve en la primera apertura: al salir de aquí se marca la
/// preferencia local con [ControladorSesion.marcarOnboardingVisto].
library;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/sesion.dart';
import '../../navegacion/rutas.dart';
import 'widgets/ilustraciones.dart';
import 'widgets/piezas.dart';

/// Las tres promesas del Reino, en el orden en que se cuentan.
@immutable
class _Promesa {
  const _Promesa({
    required this.titulo,
    required this.cuerpo,
    required this.pie,
  });

  final String titulo;
  final String cuerpo;
  final String pie;
}

const List<_Promesa> _promesas = <_Promesa>[
  _Promesa(
    titulo: 'Carga lo que quieres aprender',
    cuerpo: 'Tus apuntes, el PDF de un curso o una sola frase: '
        '"quiero aprender SQL". Con eso basta para empezar.',
    pie: 'PDF · DOCX · TXT · MD',
  ),
  _Promesa(
    titulo: 'La IA lo convierte en una ruta',
    cuerpo: 'Módulos, lecciones y desafíos ordenados de lo simple a lo '
        'difícil, citando siempre tu propio material.',
    pie: 'Tu primer módulo, listo en minutos',
  ),
  _Promesa(
    titulo: 'Aprende, sube de nivel, equipa a tu héroe',
    cuerpo: 'Cada lección te da XP y Oro de verdad. Aquí solo se gana '
        'aprendiendo: no hay atajos ni ventajas que comprar.',
    pie: 'Nivel · Dominio · Racha · Vestidor',
  ),
];

/// Pantalla de bienvenida al Reino.
class PantallaBienvenida extends StatefulWidget {
  const PantallaBienvenida({super.key});

  @override
  State<PantallaBienvenida> createState() => _PantallaBienvenidaState();
}

class _PantallaBienvenidaState extends State<PantallaBienvenida> {
  final PageController _paginas = PageController();
  int _indice = 0;

  @override
  void dispose() {
    _paginas.dispose();
    super.dispose();
  }

  bool get _esUltima => _indice == _promesas.length - 1;

  Future<void> _salir({bool aEntrar = false}) async {
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final GoRouter enrutador = GoRouter.of(context);
    await sesion.marcarOnboardingVisto();
    if (!mounted) return;
    enrutador.go(aEntrar ? '${Rutas.acceso}?modo=entrar' : Rutas.acceso);
  }

  void _avanzar() {
    if (_esUltima) {
      _salir();
      return;
    }
    if (reducirMovimiento(context)) {
      _paginas.jumpToPage(_indice + 1);
    } else {
      _paginas.nextPage(
        duration: Movimiento.transicion,
        curve: Movimiento.estandar,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final FaseSesion fase = context.select<ControladorSesion, FaseSesion>(
      (ControladorSesion s) => s.fase,
    );

    return Scaffold(
      backgroundColor: context.paleta.fondo,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: Medida.lecturaMax),
            child: fase == FaseSesion.arrancando
                ? const _Splash()
                : _onboarding(context),
          ),
        ),
      ),
    );
  }

  Widget _onboarding(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final bool quieto = reducirMovimiento(context);

    return Column(
      children: <Widget>[
        // --- Saltar -------------------------------------------------------
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Espacio.xs),
          child: Row(
            children: <Widget>[
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Text(
                  'ATENEA',
                  style: context.textos.labelLarge?.copyWith(
                    color: paleta.textoSecundario,
                    letterSpacing: 3,
                  ),
                ),
              ),
              TextButton(
                onPressed: () => _salir(),
                child: const Text('Saltar'),
              ),
            ],
          ),
        ),

        // --- Tarjetas -----------------------------------------------------
        Expanded(
          child: PageView.builder(
            controller: _paginas,
            itemCount: _promesas.length,
            onPageChanged: (int i) => setState(() => _indice = i),
            itemBuilder: (BuildContext context, int i) {
              final _Promesa promesa = _promesas[i];
              final Widget contenido = SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: Espacio.lg),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    IlustracionOnboarding(paso: i),
                    const SizedBox(height: Espacio.lg),
                    Text(promesa.titulo, style: context.textos.displaySmall),
                    const SizedBox(height: Espacio.sm),
                    Text(
                      promesa.cuerpo,
                      style: context.textos.bodyLarge?.copyWith(
                        color: paleta.textoSecundario,
                      ),
                    ),
                    const SizedBox(height: Espacio.md),
                    PildoraElastica(
                      texto: promesa.pie,
                      icono: switch (i) {
                        0 => Icons.upload_file_rounded,
                        1 => Icons.route_rounded,
                        _ => Icons.military_tech_rounded,
                      },
                      color: i == 2 ? paleta.oro : paleta.arcano,
                    ),
                  ],
                ),
              );
              if (quieto) return contenido;
              return contenido
                  .animate(key: ValueKey<int>(i))
                  .fadeIn(duration: Movimiento.transicion)
                  .slideY(begin: 0.04, end: 0, curve: Movimiento.estandar);
            },
          ),
        ),

        // --- Indicador, CTA y acceso --------------------------------------
        Padding(
          padding: const EdgeInsets.fromLTRB(
            Espacio.lg,
            Espacio.md,
            Espacio.lg,
            Espacio.md,
          ),
          child: Column(
            children: <Widget>[
              Semantics(
                label: 'Tarjeta ${_indice + 1} de ${_promesas.length}',
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    for (int i = 0; i < _promesas.length; i++)
                      AnimatedContainer(
                        duration: Movimiento.corta,
                        curve: Movimiento.estandar,
                        margin: const EdgeInsets.symmetric(
                          horizontal: Espacio.xxs,
                        ),
                        height: 6,
                        width: i == _indice ? Espacio.lg : 6,
                        decoration: BoxDecoration(
                          color: i == _indice ? paleta.oro : paleta.borde,
                          borderRadius: Redondeo.rPildora,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: Espacio.lg),
              BotonPrimario(
                texto: _esUltima ? 'Empezar' : 'Siguiente',
                icono: _esUltima
                    ? Icons.auto_awesome_rounded
                    : Icons.arrow_forward_rounded,
                alTocar: _avanzar,
              ),
              const SizedBox(height: Espacio.xs),
              TextButton(
                onPressed: () => _salir(aEntrar: true),
                child: const Text('Ya tengo cuenta'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Splash: mientras se leen los tokens y se pregunta por el héroe.
class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final bool quieto = reducirMovimiento(context);

    final Widget emblema = const EmblemaAtenea(tamano: 112);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Espacio.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (quieto)
              emblema
            else
              emblema
                  .animate()
                  .fadeIn(duration: Movimiento.transicion)
                  .scale(begin: const Offset(0.92, 0.92), end: const Offset(1, 1)),
            const SizedBox(height: Espacio.lg),
            Text('Atenea', style: context.textos.displayMedium),
            const SizedBox(height: Espacio.xs),
            Text(
              'Convierte cualquier conocimiento en una aventura',
              textAlign: TextAlign.center,
              style: context.textos.bodyLarge?.copyWith(
                color: paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.xl),
            SizedBox(
              width: Espacio.xxl * 3,
              child: Semantics(
                label: 'Abriendo las puertas del Reino',
                child: const LinearProgressIndicator(
                  minHeight: 4,
                  borderRadius: Redondeo.rPildora,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
