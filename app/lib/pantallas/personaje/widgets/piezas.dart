/// Piezas compartidas por el grupo Personaje, Mercado, Perfil, Racha y
/// Ajustes.
///
/// Aquí viven los pequeños componentes que se repiten entre P15, P16, P17,
/// P18 y P21: el contador de oro del encabezado, las fichas de estadística,
/// la lista de requisitos de un ítem bloqueado, los esqueletos de carga y los
/// formateadores de cifras y fechas en español.
///
/// Nada de esto calcula valores de juego: solo da forma a lo que envía el
/// Reino.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';
import '../../../estado/panel.dart';
import '../../../estado/personaje.dart';
import '../../../estado/sesion.dart';

// ---------------------------------------------------------------------------
// Formato
// ---------------------------------------------------------------------------

final NumberFormat _formatoCifra = NumberFormat.decimalPattern('es');

/// Cifra con separador de miles en español ("1.240").
String cifra(num valor) => _formatoCifra.format(valor);

const List<String> _mesesCortos = <String>[
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
];

const List<String> _mesesLargos = <String>[
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
];

/// Nombre largo del mes (1–12).
String nombreDeMes(int mes) => _mesesLargos[(mes - 1).clamp(0, 11)];

/// Fecha corta en español ("10 sep").
String fechaCorta(DateTime dia) =>
    '${dia.day} ${_mesesCortos[(dia.month - 1).clamp(0, 11)]}';

/// Fecha con año ("10 sep 2026").
String fechaConAno(DateTime dia) => '${fechaCorta(dia)} ${dia.year}';

/// Inicial del día de la semana, empezando el lunes (L M X J V S D).
const List<String> inicialesDeDia = <String>['L', 'M', 'X', 'J', 'V', 'S', 'D'];

/// Nombre del día de la semana para el lector de pantalla.
const List<String> nombresDeDia = <String>[
  'lunes',
  'martes',
  'miércoles',
  'jueves',
  'viernes',
  'sábado',
  'domingo',
];

/// Tiempo legible a partir de segundos ("3h 10m").
String tiempoLegible(int segundos) {
  if (segundos < 60) return '0m';
  final int horas = segundos ~/ 3600;
  final int minutos = (segundos % 3600) ~/ 60;
  if (horas == 0) return '${minutos}m';
  return '${horas}h ${minutos}m';
}

/// Cuenta atrás legible ("5h 12m", "12m").
String cuentaAtras(int segundos) {
  if (segundos <= 0) return 'ya mismo';
  final int horas = segundos ~/ 3600;
  final int minutos = (segundos % 3600) ~/ 60;
  if (horas == 0) return '${minutos}m';
  return '${horas}h ${minutos}m';
}

// ---------------------------------------------------------------------------
// Ítems: ranuras, rarezas e iconos
// ---------------------------------------------------------------------------

/// Las seis ranuras que el MVP muestra alrededor del avatar (§P16).
const List<RanuraItem> ranurasDelVestidor = <RanuraItem>[
  RanuraItem.cabeza,
  RanuraItem.cuerpo,
  RanuraItem.arma,
  RanuraItem.secundaria,
  RanuraItem.capa,
  RanuraItem.accesorio,
];

/// Nombre visible de la ranura, con el término del glosario para la mano
/// secundaria.
String nombreRanura(RanuraItem ranura) =>
    ranura == RanuraItem.secundaria ? 'Escudo' : ranura.etiqueta;

/// Icono con el que se representa cada ranura mientras no exista el arte.
IconData iconoDeRanura(RanuraItem ranura) => switch (ranura) {
      RanuraItem.cabeza => Icons.sports_motorsports_rounded,
      RanuraItem.cuerpo => Icons.checkroom_rounded,
      RanuraItem.capa => Icons.dry_cleaning_rounded,
      RanuraItem.guantes => Icons.back_hand_rounded,
      RanuraItem.botas => Icons.hiking_rounded,
      RanuraItem.arma => Icons.auto_fix_high_rounded,
      RanuraItem.secundaria => Icons.shield_rounded,
      RanuraItem.accesorio => Icons.diamond_rounded,
      RanuraItem.mascota => Icons.pets_rounded,
      RanuraItem.montura => Icons.emoji_nature_rounded,
    };

/// Traduce la rareza del contrato a la rareza visual de los tokens.
Rareza rarezaVisualDe(RarezaItem rareza) => Rareza.desdeApi(rareza.api);

/// Primer requisito que todavía no se cumple; si están todos cumplidos,
/// devuelve el primero de la lista (o nulo si no hay ninguno).
Requisito? requisitoPendiente(List<Requisito> requisitos) {
  for (final Requisito r in requisitos) {
    if (!r.cumplido) return r;
  }
  return requisitos.isEmpty ? null : requisitos.first;
}

/// Color del estado de dominio, siempre acompañado de su etiqueta textual.
Color colorDeDominio(BuildContext context, EstadoDominio estado) =>
    switch (estado) {
      EstadoDominio.dominado => context.paleta.exito,
      EstadoDominio.enProgreso => context.paleta.dominio,
      EstadoDominio.enRiesgo => context.paleta.advertencia,
      EstadoDominio.debilitado => context.paleta.brasa,
      EstadoDominio.sinEvidencia => context.paleta.textoSecundario,
    };

// ---------------------------------------------------------------------------
// Contador de oro
// ---------------------------------------------------------------------------

/// Píldora con el saldo de oro, con el número animado al cambiar.
class ContadorOro extends StatelessWidget {
  const ContadorOro({
    required this.saldo,
    super.key,
    this.alTocar,
    this.grande = false,
  });

  /// Saldo tal como lo calcula el servidor.
  final int saldo;

  /// Acción opcional (por ejemplo, abrir el Mercado).
  final VoidCallback? alTocar;

  /// Versión destacada para encabezados de sección.
  final bool grande;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Widget contenido = Container(
      constraints: const BoxConstraints(minHeight: Medida.areaTactilMin),
      padding: const EdgeInsets.symmetric(horizontal: Espacio.sm),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            Icons.monetization_on_rounded,
            size: grande ? 24 : 20,
            color: p.oro,
          ),
          const SizedBox(width: Espacio.xxs + 2),
          CifraAnimada(
            valor: saldo,
            estilo: (grande ? Cifras.media(context) : Cifras.pequena(context))
                .copyWith(color: p.oro),
          ),
        ],
      ),
    );

    return Semantics(
      label: '$saldo de oro',
      button: alTocar != null,
      excludeSemantics: true,
      child: Material(
        color: p.oro.withValues(alpha: 0.10),
        borderRadius: Redondeo.rPildora,
        child: InkWell(
          onTap: alTocar,
          borderRadius: Redondeo.rPildora,
          child: contenido,
        ),
      ),
    );
  }
}

/// Contador de oro que se abastece del estado disponible: primero el Mercado,
/// después el panel y, como último recurso, el personaje de la sesión.
class ContadorOroActual extends StatelessWidget {
  const ContadorOroActual({super.key, this.alTocar});

  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final ControladorPersonaje personaje = context.watch<ControladorPersonaje>();
    final ControladorPanel panel = context.watch<ControladorPanel>();
    final ControladorSesion sesion = context.watch<ControladorSesion>();

    final int saldo;
    if (personaje.tienda != null || personaje.ultimaCompra != null) {
      saldo = personaje.saldo;
    } else if (panel.hayDatos) {
      saldo = panel.saldoOro;
    } else {
      saldo = sesion.personaje?.saldoOro ?? 0;
    }

    return Padding(
      padding: const EdgeInsets.only(right: Espacio.xs),
      child: ContadorOro(saldo: saldo, alTocar: alTocar),
    );
  }
}

// ---------------------------------------------------------------------------
// Estadísticas
// ---------------------------------------------------------------------------

/// Ficha de estadística con icono libre, hermana de [FichaMedallon].
///
/// Se usa para las dos estadísticas héroe del perfil que no encajan en los
/// seis medallones del sistema (Logros e Ítems).
class FichaEstadistica extends StatelessWidget {
  const FichaEstadistica({
    required this.icono,
    required this.color,
    required this.valor,
    required this.etiqueta,
    super.key,
    this.alTocar,
  });

  final IconData icono;
  final Color color;
  final String valor;
  final String etiqueta;
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    return TarjetaAtenea(
      alTocar: alTocar,
      padding: const EdgeInsets.symmetric(
        horizontal: Espacio.sm,
        vertical: Espacio.sm,
      ),
      semantica: '$etiqueta: $valor',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icono, size: 20, color: color),
          const SizedBox(height: Espacio.xs),
          Text(valor, style: Cifras.media(context)),
          Text(
            etiqueta,
            style: context.textos.bodySmall?.copyWith(
              color: context.paleta.textoSecundario,
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Requisitos
// ---------------------------------------------------------------------------

/// Lista de condiciones de desbloqueo con su progreso: lo que motiva a seguir.
class ListaRequisitos extends StatelessWidget {
  const ListaRequisitos({required this.requisitos, super.key});

  final List<Requisito> requisitos;

  @override
  Widget build(BuildContext context) {
    if (requisitos.isEmpty) return const SizedBox.shrink();
    final AteneaPalette p = context.paleta;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (final Requisito r in requisitos)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: Semantics(
              label: '${r.etiqueta}. '
                  '${r.cumplido ? 'Cumplido' : 'Te falta completarlo'}',
              excludeSemantics: true,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Icon(
                        r.cumplido
                            ? Icons.check_circle_rounded
                            : Icons.lock_outline_rounded,
                        size: 18,
                        color: r.cumplido ? p.exito : p.textoSecundario,
                      ),
                      const SizedBox(width: Espacio.xs),
                      Expanded(
                        child: Text(
                          r.etiqueta.isEmpty ? r.tipo.etiqueta : r.etiqueta,
                          style: context.textos.bodyMedium?.copyWith(
                            color:
                                r.cumplido ? p.textoPrimario : p.textoSecundario,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (!r.cumplido && r.objetivo > 0) ...<Widget>[
                    const SizedBox(height: Espacio.xxs + 2),
                    Padding(
                      padding: const EdgeInsets.only(left: Espacio.lg + 2),
                      child: BarraProgreso(
                        valor: r.fraccion,
                        alto: 6,
                        color: p.dominio,
                        textoDerecha:
                            '${cifra(r.actual.round())} / ${cifra(r.objetivo.round())}',
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Avisos y esqueletos
// ---------------------------------------------------------------------------

/// Banda discreta para avisos que no bloquean la pantalla (caché, error al
/// guardar, sin conexión).
class BandaAviso extends StatelessWidget {
  const BandaAviso({
    required this.mensaje,
    super.key,
    this.icono = Icons.info_outline_rounded,
    this.color,
    this.textoAccion,
    this.alTocarAccion,
  });

  final String mensaje;
  final IconData icono;
  final Color? color;
  final String? textoAccion;
  final VoidCallback? alTocarAccion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color c = color ?? p.advertencia;
    return Container(
      margin: const EdgeInsets.only(bottom: Espacio.sm),
      padding: const EdgeInsets.symmetric(
        horizontal: Espacio.sm,
        vertical: Espacio.xs,
      ),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: Redondeo.rBoton,
        border: Border.all(color: c.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 18, color: c),
          const SizedBox(width: Espacio.xs),
          Expanded(
            child: Text(
              mensaje,
              style: context.textos.bodyMedium?.copyWith(color: p.textoPrimario),
            ),
          ),
          if (textoAccion != null)
            TextButton(onPressed: alTocarAccion, child: Text(textoAccion!)),
        ],
      ),
    );
  }
}

/// Muestra un aviso breve al pie de la pantalla.
void avisar(BuildContext context, String mensaje, {bool esError = false}) {
  final AteneaPalette p = context.paleta;
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Row(
          children: <Widget>[
            Icon(
              esError
                  ? Icons.error_outline_rounded
                  : Icons.check_circle_outline_rounded,
              size: 20,
              color: esError ? p.error : p.exito,
            ),
            const SizedBox(width: Espacio.xs),
            Expanded(child: Text(mensaje)),
          ],
        ),
        duration: const Duration(seconds: 3),
      ),
    );
}

/// Esqueleto de una tarjeta de ítem, del alto de la cuadrícula real.
class EsqueletoItem extends StatelessWidget {
  const EsqueletoItem({super.key});

  @override
  Widget build(BuildContext context) {
    return TarjetaAtenea(
      padding: const EdgeInsets.all(Espacio.sm),
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const AspectRatio(
            aspectRatio: 1,
            child: Esqueleto(alto: double.infinity, radio: Redondeo.chip),
          ),
          const SizedBox(height: Espacio.xs),
          const Esqueleto(alto: 14),
          const SizedBox(height: Espacio.xxs),
          Align(
            alignment: Alignment.centerLeft,
            child: Esqueleto(alto: 12, ancho: 64),
          ),
        ],
      ),
    );
  }
}

/// Bloque de líneas de esqueleto para listas y tarjetas de texto.
class EsqueletoFilas extends StatelessWidget {
  const EsqueletoFilas({super.key, this.filas = 3, this.alto = 56});

  final int filas;
  final double alto;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        for (int i = 0; i < filas; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: Esqueleto(alto: alto, radio: Redondeo.tarjeta),
          ),
      ],
    );
  }
}
