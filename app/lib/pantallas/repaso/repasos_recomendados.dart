/// Repasos recomendados: los temas que se te están olvidando.
///
/// El servidor ya calcula el decaimiento real por tema (§7.6) y sirve
/// `GET /reviews/recommended` completo, con duración estimada de cada
/// repaso — pero ninguna pantalla lo pedía. Fuera de un desafío de módulo
/// reprobado (que solo sugiere los temas flojos de *ese* intento puntual) o
/// de terminar una Ruta entera, el aprendiz nunca veía esta lista mientras
/// estudiaba con normalidad.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/leccion.dart';
import '../../navegacion/rutas.dart';
import '../inicio/widgets/esqueletos.dart';
import 'widgets/tarjeta_repaso.dart';

/// Lista completa de temas en riesgo o débiles, con acceso directo a
/// repasarlos.
class PantallaRepasosRecomendados extends StatefulWidget {
  const PantallaRepasosRecomendados({super.key});

  @override
  State<PantallaRepasosRecomendados> createState() =>
      _PantallaRepasosRecomendadosState();
}

class _PantallaRepasosRecomendadosState
    extends State<PantallaRepasosRecomendados> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.read<ControladorLeccion>().cargarRepasosRecomendados();
    });
  }

  @override
  Widget build(BuildContext context) {
    final ControladorLeccion control = context.watch<ControladorLeccion>();
    final List<SugerenciaRepaso> sugerencias = control.repasosRecomendados;
    final bool cargaInicial = control.cargandoRepasos && sugerencias.isEmpty;

    return PantallaAtenea(
      titulo: 'Repasos recomendados',
      mostrarVolver: true,
      cuerpo: RefreshIndicator(
        onRefresh: () => control.cargarRepasosRecomendados(forzar: true),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.only(top: Espacio.xs, bottom: Espacio.xxl),
          children: <Widget>[
            if (cargaInicial)
              const ListaEsqueleto(filas: 4, lineas: 2)
            else if (control.errorRepasos != null && sugerencias.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: Espacio.xl),
                child: EstadoError(
                  titulo: 'No pudimos traer tus repasos',
                  mensaje: control.errorRepasos!.mensaje,
                  alReintentar: () =>
                      control.cargarRepasosRecomendados(forzar: true),
                ),
              )
            else if (sugerencias.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: Espacio.xl),
                child: EstadoVacio(
                  icono: Icons.check_circle_outline_rounded,
                  titulo: 'Nada pendiente de repasar',
                  mensaje:
                      'Todo lo que has estudiado sigue firme. Vuelve por aquí '
                      'de vez en cuando: el Reino avisa apenas algo empieza a '
                      'olvidarse.',
                ),
              )
            else ...<Widget>[
              for (final SugerenciaRepaso s in sugerencias)
                TarjetaRepaso(
                  sugerencia: s,
                  alTocar: () => context.push(Rutas.repaso(s.temaId)),
                ),
              const SizedBox(height: Espacio.sm),
              _PiePagina(control: control),
            ],
          ],
        ),
      ),
    );
  }
}

/// Botón "Cargar más", su giro de espera, o el error de una página siguiente.
class _PiePagina extends StatelessWidget {
  const _PiePagina({required this.control});

  final ControladorLeccion control;

  @override
  Widget build(BuildContext context) {
    if (control.cargandoMasRepasos) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: Espacio.md),
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(strokeWidth: 2.5),
          ),
        ),
      );
    }
    if (!control.hayMasRepasos) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: Espacio.xs),
      child: Column(
        children: <Widget>[
          if (control.errorRepasos != null)
            Padding(
              padding: const EdgeInsets.only(bottom: Espacio.xs),
              child: Text(
                control.errorRepasos!.mensaje,
                style: context.textos.bodySmall?.copyWith(
                  color: context.paleta.error,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          Center(
            child: TextButton.icon(
              onPressed: control.cargarMasRepasos,
              icon: const Icon(Icons.expand_more_rounded),
              label: const Text('Cargar más'),
            ),
          ),
        ],
      ),
    );
  }
}
