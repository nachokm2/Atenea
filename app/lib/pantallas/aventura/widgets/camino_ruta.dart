/// El camino de la Ruta: los nodos de P07, sin la pantalla alrededor.
///
/// Esto vivía dentro de `_PantallaMapaRutaState` y por eso **no había forma de
/// probarlo**. Montar la pantalla entera exige el proveedor, el enrutador y una
/// llamada de red, así que ninguna prueba llegaba hasta aquí. El coste real de
/// eso se midió: quitando el nodo del Desafío del camino —literalmente el fallo
/// que se acababa de arreglar— la suite entera del cliente seguía verde.
///
/// Dos cosas viven aquí y son lo que se prueba:
///
/// * `CaminoDeLaRuta`, que decide **qué nodos existen** y en qué orden.
/// * Las tres reglas de estilo, que son funciones puras: traducen el sobre del
///   servidor —`can_start`, `content_status`, `passed`, el bloqueo del módulo—
///   a lo que se ve. Son la única consumidora de la mitad de
///   `ModuleAssessmentOut`, y como no dependen de `context` ni de estado, se
///   comprueban sin montar nada.
///
/// La pantalla se queda con lo suyo: pedir los datos, la cabecera, los avisos y
/// qué ocurre al tocar.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import 'comunes_aventura.dart';
import 'nodos_mapa.dart';

// -------------------------------------------------------------------------
// Las reglas de estilo. Puras: mismos datos, mismo resultado.
// -------------------------------------------------------------------------

/// Cómo se pinta el nodo de un módulo.
///
/// El orden importa: «en construcción» se comprueba **antes** que «actual» y
/// «disponible», así que un módulo cuyo `content_status` no llegue arrastra a
/// todo el resto. Es justo lo que pasaba cuando el servidor no mandaba el
/// campo: el cliente lo leía nulo, caía a `pending` y pintaba todos los
/// módulos como si el Reino los estuviera escribiendo.
EstiloNodo estiloDeModulo(DetalleRuta detalle, ModuloRuta modulo) {
  if (modulo.estado == EstadoModulo.completado ||
      modulo.estado == EstadoModulo.dominado) {
    return EstiloNodo.completado;
  }
  if (modulo.estaBloqueado) return EstiloNodo.bloqueado;
  if (modulo.enConstruccion) return EstiloNodo.enConstruccion;
  if (detalle.moduloActual?.id == modulo.id) return EstiloNodo.actual;
  return EstiloNodo.disponible;
}

/// Cómo se pinta el nodo de una lección.
EstiloNodo estiloDeLeccion(
  ModuloRuta modulo,
  ResumenLeccion leccion, {
  required bool esSiguiente,
}) {
  if (leccion.estaCompletada) return EstiloNodo.completado;
  if (modulo.estaBloqueado) return EstiloNodo.bloqueado;
  if (!leccion.estaLista) return EstiloNodo.enConstruccion;
  return esSiguiente ? EstiloNodo.actual : EstiloNodo.disponible;
}

/// Cómo se pinta el nodo de la prueba del módulo.
///
/// Traduce el sobre entero: si ya la aprobó, si el módulo está bloqueado, si el
/// banco de preguntas todavía se está escribiendo, y si el servidor autoriza
/// empezar ahora —que es cosa del enfriamiento y del cupo del día, no del
/// bloqueo del módulo (§7.5)—. El último tramo distingue «puedes presentarte
/// ya» de «te faltan lecciones»: con todas las lecciones hechas, el nodo late.
EstiloNodo estiloDeDesafio(ModuloRuta modulo, ResumenEvaluacion evaluacion) {
  if (evaluacion.aprobada) return EstiloNodo.completado;
  if (modulo.estaBloqueado) return EstiloNodo.bloqueado;
  if (!evaluacion.estadoContenido.estaDisponible) {
    return EstiloNodo.enConstruccion;
  }
  if (!evaluacion.puedeEmpezar) return EstiloNodo.bloqueado;
  final bool listasTodas = modulo.leccionesTotales > 0 &&
      modulo.leccionesCompletadas >= modulo.leccionesTotales;
  return listasTodas ? EstiloNodo.actual : EstiloNodo.disponible;
}

/// La primera lección que se puede abrir y todavía no está hecha.
ResumenLeccion? primeraPendiente(List<ResumenLeccion> lecciones) {
  for (final ResumenLeccion leccion in lecciones) {
    if (!leccion.estaCompletada && leccion.estaLista) return leccion;
  }
  return null;
}

// -------------------------------------------------------------------------
// El camino
// -------------------------------------------------------------------------

/// La senda vertical de la Ruta: módulos, sus lecciones, su prueba y el tesoro.
class CaminoDeLaRuta extends StatelessWidget {
  const CaminoDeLaRuta({
    required this.detalle,
    required this.expandido,
    required this.alTocarModulo,
    required this.alTocarLeccion,
    required this.alTocarDesafio,
    required this.alTocarReto,
    required this.alVerLaForja,
    super.key,
  });

  /// La ruta completa tal y como la sirve el servidor.
  final DetalleRuta detalle;

  /// Si un módulo muestra sus lecciones. Lo decide la pantalla, porque es
  /// estado de interacción y sobrevive a los redibujados.
  final bool Function(ModuloRuta modulo) expandido;

  final void Function(ModuloRuta modulo) alTocarModulo;
  final void Function(ModuloRuta modulo, ResumenLeccion leccion, EstiloNodo estilo)
      alTocarLeccion;
  final void Function(
    ModuloRuta modulo,
    ResumenEvaluacion evaluacion,
    EstiloNodo estilo,
  ) alTocarDesafio;

  /// El Reto opcional del módulo, ya completado.
  final void Function(ModuloRuta modulo) alTocarReto;

  /// Salida cuando la ruta no tiene ni un módulo todavía.
  final VoidCallback alVerLaForja;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: nodos(context),
    );
  }

  /// Los nodos del camino, en orden.
  ///
  /// Público y separado de `build` para que la pantalla los pueda meter
  /// directamente en su `ListView` —que es lo que hacía antes— sin anidar un
  /// `Column` dentro de una lista desplazable.
  List<Widget> nodos(BuildContext context) {
    final List<ModuloRuta> modulos = detalle.modulos;

    if (modulos.isEmpty) {
      return <Widget>[
        EstadoVacio(
          icono: Icons.map_outlined,
          titulo: 'El camino aún no está trazado',
          mensaje: 'El Reino todavía no ha dibujado los módulos de esta ruta.',
          textoAccion: 'Ver el avance de la forja',
          alTocarAccion: alVerLaForja,
        ),
      ];
    }

    final List<Widget> nodos = <Widget>[];
    int indice = 0;

    for (int i = 0; i < modulos.length; i++) {
      final ModuloRuta modulo = modulos[i];
      final EstiloNodo estilo = estiloDeModulo(detalle, modulo);
      final bool hecho = estilo == EstiloNodo.completado;
      final bool anteriorHecho = i == 0
          ? false
          : estiloDeModulo(detalle, modulos[i - 1]) == EstiloNodo.completado;
      final bool abierto = expandido(modulo);
      final List<ResumenLeccion> lecciones = modulo.todasLasLecciones;
      final ResumenLeccion? siguiente = primeraPendiente(lecciones);

      nodos.add(
        AparecerEnCascada(
          indice: indice++,
          hijo: NodoCamino(
            estilo: estilo,
            grande: true,
            lineaArriba: i > 0,
            tramoSuperiorHecho: anteriorHecho,
            tramoInferiorHecho: hecho,
            icono: estilo == EstiloNodo.completado
                ? Icons.check_rounded
                : (estilo == EstiloNodo.bloqueado
                    ? Icons.lock_rounded
                    : Icons.castle_rounded),
            hijo: ContenidoModulo(
              modulo: modulo,
              estilo: estilo,
              expandido: abierto,
              alTocar: () => alTocarModulo(modulo),
            ),
          ),
        ),
      );

      if (!abierto) continue;

      for (final ResumenLeccion leccion in lecciones) {
        final EstiloNodo estiloLeccion = estiloDeLeccion(
          modulo,
          leccion,
          esSiguiente: siguiente?.id == leccion.id,
        );
        nodos.add(
          AparecerEnCascada(
            indice: indice++,
            hijo: NodoCamino(
              estilo: estiloLeccion,
              sangria: Espacio.md,
              tramoSuperiorHecho: hecho,
              tramoInferiorHecho: hecho,
              hijo: ContenidoLeccion(
                leccion: leccion,
                estilo: estiloLeccion,
                alTocar: () => alTocarLeccion(modulo, leccion, estiloLeccion),
              ),
            ),
          ),
        );
      }

      final ResumenEvaluacion? evaluacion = modulo.evaluacion;
      if (evaluacion != null) {
        final EstiloNodo estiloDesafio = estiloDeDesafio(modulo, evaluacion);
        nodos.add(
          AparecerEnCascada(
            indice: indice++,
            hijo: NodoCamino(
              estilo: estiloDesafio,
              sangria: Espacio.xs,
              icono: Icons.shield_rounded,
              tramoSuperiorHecho: hecho,
              tramoInferiorHecho: hecho,
              hijo: ContenidoDesafio(
                evaluacion: evaluacion,
                estilo: estiloDesafio,
                alTocar: () => alTocarDesafio(modulo, evaluacion, estiloDesafio),
              ),
            ),
          ),
        );
      }

      // Reto opcional: solo tras completar el módulo. El servidor no manda
      // si ya se agotó (content.challenges_per_module_max) — se ofrece
      // siempre que el módulo esté hecho, y el 409 CHALLENGE_ALREADY_USED
      // avisa al tocarlo si ya no queda.
      if (hecho) {
        nodos.add(
          AparecerEnCascada(
            indice: indice++,
            hijo: NodoCamino(
              estilo: EstiloNodo.disponible,
              sangria: Espacio.xs,
              icono: Icons.military_tech_rounded,
              tramoSuperiorHecho: hecho,
              tramoInferiorHecho: hecho,
              hijo: ContenidoReto(alTocar: () => alTocarReto(modulo)),
            ),
          ),
        );
      }
    }

    final bool completada = detalle.ruta.estado == EstadoRuta.completada;
    nodos.add(
      AparecerEnCascada(
        indice: indice,
        hijo: NodoCamino(
          estilo: completada ? EstiloNodo.completado : EstiloNodo.bloqueado,
          grande: true,
          lineaAbajo: false,
          tramoSuperiorHecho: completada,
          icono: completada
              ? Icons.emoji_events_rounded
              : Icons.workspace_premium_outlined,
          hijo: ContenidoTesoro(
            completada: completada,
            item: detalle.itemDeConocimiento,
          ),
        ),
      ),
    );

    return nodos;
  }
}
